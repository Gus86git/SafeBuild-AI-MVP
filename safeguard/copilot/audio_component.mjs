// No credentials or provider requests in this component. Audio crosses only
// the Streamlit trigger boundary; Python validates and transcribes it.
export const STATES = Object.freeze(['IDLE','REQUESTING_PERMISSION','RECORDING','STOPPING','TRANSCRIBING','PROCESSING','SPEAKING','ERROR']);
export class RecorderMachine {
  constructor(api, notify, submit) { this.api=api; this.notify=notify; this.submit=submit; this.state='IDLE'; this.epoch=0; this.held=false; this.stream=null; this.recorder=null; this.timer=null; this.disposed=false; }
  set(state, message='') { this.state=state; this.notify(state,message); }
  tracks(stream=this.stream) { if(stream) stream.getTracks().forEach(t=>t.stop()); if(stream===this.stream) this.stream=null; }
  async start() {
    if(this.disposed || !['IDLE','ERROR','SPEAKING'].includes(this.state)) return;
    this.api.stopSpeech(); this.held=true; const epoch=++this.epoch;
    this.set('REQUESTING_PERMISSION');
    try {
      const stream=await this.api.getMedia();
      if(this.disposed || epoch!==this.epoch || !this.held) { this.tracks(stream); return; }
      this.stream=stream; const recorder=this.api.createRecorder(stream); this.recorder=recorder;
      const chunks=[]; let size=0;
      recorder.ondataavailable=e=>{ if(epoch!==this.epoch || !e.data?.size) return; size+=e.data.size; if(size>2000000) this.cancel('La grabación supera el límite.'); else chunks.push(e.data); };
      recorder.onerror=()=>this.cancel('La grabación se interrumpió. Intentá nuevamente.');
      recorder.onstop=async()=>{
        this.tracks(stream); clearTimeout(this.timer);
        if(this.disposed || epoch!==this.epoch) return;
        if(!chunks.length) {this.set('ERROR','La grabación está vacía.');return;}
        this.set('STOPPING');
        try {
          const audio=await this.api.encode(chunks,recorder.mimeType);
          if(this.disposed || epoch!==this.epoch) return;
          this.set('TRANSCRIBING'); this.submit(audio);
        } catch { if(epoch===this.epoch && !this.disposed) this.set('ERROR','No se pudo preparar el audio. Grabá entre 0,6 y 30 segundos.'); }
      };
      recorder.start(250); this.set('RECORDING');
      this.timer=setTimeout(()=>this.stop(),30000);
      stream.getTracks().forEach(t=>{t.onended=()=>{if(this.state==='RECORDING')this.cancel('El micrófono se desconectó.');};});
    } catch { if(epoch===this.epoch && !this.disposed) {this.tracks();this.set('ERROR','No se pudo acceder al micrófono. Revisá sus permisos y conexión.');} }
  }
  stop() {
    this.held=false;
    if(this.state==='REQUESTING_PERMISSION') {++this.epoch;this.set('IDLE');return;}
    if(this.state!=='RECORDING') return;
    this.set('STOPPING'); clearTimeout(this.timer);
    try { this.recorder.stop(); } catch {this.cancel('No se pudo finalizar la grabación.');}
    this.tracks();
  }
  cancel(message='Grabación cancelada.') {
    this.held=false; ++this.epoch; clearTimeout(this.timer);
    try {if(this.recorder?.state==='recording')this.recorder.stop();} catch {}
    this.tracks(); this.set(message?'ERROR':'IDLE',message);
  }
  dispose() {this.disposed=true;this.cancel('');}
}

export function pcmWav(samples, rate=16000) {
  const buffer=new ArrayBuffer(44+samples.length*2), view=new DataView(buffer);
  const str=(offset,value)=>{for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i));};
  str(0,'RIFF');view.setUint32(4,36+samples.length*2,true);str(8,'WAVE');str(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,rate,true);view.setUint32(28,rate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  str(36,'data');view.setUint32(40,samples.length*2,true);
  samples.forEach((sample,i)=>view.setInt16(44+i*2,Math.round(Math.max(-1,Math.min(1,sample))*(sample<0?32768:32767)),true));
  return new Uint8Array(buffer);
}

async function encodeAudio(chunks, type) {
  const blob=new Blob(chunks,{type});
  if(blob.size>2000000) throw Error('size');
  const Audio=window.AudioContext||window.webkitAudioContext;
  const ctx=new Audio();
  try {
    const decoded=await ctx.decodeAudioData(await blob.arrayBuffer());
    if(decoded.duration<.6 || decoded.duration>30.1) throw Error('duration');
    const offline=new OfflineAudioContext(1,Math.min(480000,Math.round(decoded.duration*16000)),16000);
    const source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start();
    const rendered=await offline.startRendering();const bytes=pcmWav(rendered.getChannelData(0));
    let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    return btoa(binary);
  } finally { await ctx.close(); }
}

const played=new Set();
const mounted=new WeakMap();
const drafts=new WeakMap();
let activePlayer=null;
export function shouldAutoPlay(mode,id,seen=played){ if(mode!=='voice'||seen.has(id))return false;seen.add(id);return true; }
export function chooseVoice(voices){return voices.filter(v=>v.localService&&/^es(?:-|$)/i.test(v.lang)).sort((a,b)=>Number(/^es-AR$/i.test(b.lang))-Number(/^es-AR$/i.test(a.lang)))[0];}
function stopSpeech(){if(activePlayer)activePlayer.stop();else window.speechSynthesis?.cancel();}
const icons={mic:'<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',send:'<circle cx="12" cy="12" r="9"/><path d="M12 17V7m-4 4 4-4 4 4"/>',speaker:'<path d="m3 9 5 0 5-5v16l-5-5H3zM17 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',stop:'<rect x="5" y="5" width="14" height="14" rx="2"/>',pause:'<path d="M8 4v16M16 4v16"/>',play:'<path d="m6 3 15 9-15 9z"/>',cancel:'<path d="m5 5 14 14M19 5 5 19"/>'};
const svg=name=>`<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
const labels={IDLE:'',REQUESTING_PERMISSION:'Esperando permiso del micrófono…',RECORDING:'Grabando · soltá para enviar',STOPPING:'Preparando audio…',TRANSCRIBING:'Transcribiendo audio…',PROCESSING:'Consultando fuentes…',SPEAKING:'Leyendo respuesta…',ERROR:''};

export default function({parentElement:root,data,setTriggerValue}) {
  // Dispose the previous renderer on data updates as well as actual unmount.
  mounted.get(root)?.();
  // Streamlit owns the initial markup, including style wrappers. Only remove
  // nodes created by this renderer; never clear its parent/shadow root.
  const originalNodes=new Set(root.children);
  const managed=fn=>{let cleaned=false;const cleanup=()=>{if(cleaned)return;cleaned=true;fn();for(const child of Array.from(root.children)){if(!originalNodes.has(child))child.remove();}if(mounted.get(root)===cleanup)mounted.delete(root);};mounted.set(root,cleanup);return cleanup;};
  const abort=new AbortController(), options={signal:abort.signal};
  const el=(tag,cls,text)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(text)x.textContent=text;return x;};
  const btn=(name,title)=>{const x=el('button','icon-button');x.type='button';x.innerHTML=svg(name);x.title=title;x.setAttribute('aria-label',title);return x;};
  const status=el('div','voice-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  if(data.kind==='player') {
    const wrap=el('div','player');const speak=btn('speaker','Escuchar respuesta'),pause=btn('pause','Pausar lectura'),resume=btn('play','Reanudar lectura'),stop=btn('stop','Detener lectura'),copy=btn('copy','Copiar respuesta');
    const speed=el('select','speed');speed.setAttribute('aria-label','Velocidad de lectura');
    [.8,1,1.2,1.5].forEach(n=>{const o=el('option','',`${n.toFixed(1)}×`);o.value=n;speed.append(o);});speed.value='1';
    wrap.append(speak,pause,resume,stop,copy,speed);root.append(wrap,status);
    let state='IDLE',utterance=null,watchdog=null,disposed=false;
    const set=(next,message='')=>{state=next;speak.hidden=next==='SPEAKING'||next==='PAUSED';pause.hidden=next!=='SPEAKING';resume.hidden=next!=='PAUSED';stop.hidden=!['SPEAKING','PAUSED'].includes(next);status.textContent=message;};set('IDLE');
    const player={stop:()=>{clearTimeout(watchdog);if(activePlayer===player){window.speechSynthesis?.cancel();activePlayer=null;}set('IDLE');}};
    const read=()=>{
      stopSpeech();if(!window.speechSynthesis||!window.SpeechSynthesisUtterance){set('ERROR','Lectura no disponible en este navegador.');return;}
      const voice=chooseVoice(window.speechSynthesis.getVoices());
      if(!voice){set('ERROR','No hay una voz española local disponible. Instalá una voz de español en el sistema y volvé a intentar.');return;}
      utterance=new SpeechSynthesisUtterance(data.text);utterance.lang=voice.lang;utterance.voice=voice;utterance.rate=Number(speed.value);
      activePlayer=player;
      utterance.onstart=()=>{clearTimeout(watchdog);if(!disposed)set('SPEAKING',`Voz local: ${voice.name} (${voice.lang})`);};
      utterance.onend=()=>{clearTimeout(watchdog);if(activePlayer===player)activePlayer=null;if(!disposed)set('IDLE');};
      utterance.onerror=()=>{clearTimeout(watchdog);if(activePlayer===player)activePlayer=null;if(!disposed)set('ERROR','No se pudo iniciar o continuar la lectura. Usá Escuchar respuesta.');};
      try {window.speechSynthesis.speak(utterance);watchdog=setTimeout(()=>{if(state!=='SPEAKING'&&activePlayer===player){player.stop();set('ERROR','El navegador no inició la lectura. Pulsá Escuchar respuesta.');}},1800);} catch {set('ERROR','Lectura bloqueada. Pulsá Escuchar respuesta.');}
    };
    speak.addEventListener('click',read,options);
    pause.addEventListener('click',()=>{window.speechSynthesis.pause();set('PAUSED','Lectura pausada.');},options);
    resume.addEventListener('click',()=>{window.speechSynthesis.resume();set('SPEAKING','Leyendo respuesta…');},options);
    stop.addEventListener('click',player.stop,options);
    copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(data.text);status.textContent='Respuesta copiada.';}catch{status.textContent='No se pudo copiar. Seleccioná el texto visible.';}},options);
    window.addEventListener('pagehide',player.stop,options);
    // IDs only, never text/audio. Mark before attempting playback so reruns do not replay.
    if(shouldAutoPlay(data.mode,data.id)) read();
    return managed(()=>{disposed=true;abort.abort();clearTimeout(watchdog);if(activePlayer===player)player.stop();});
  }
  const form=el('form','composer'),input=el('input','question'),mic=btn('mic','Mantener pulsado para hablar'),send=btn('send','Enviar pregunta'),cancel=btn('cancel','Cancelar grabación');
  const previous=drafts.get(root),seed=data.draft||'';
  input.type='text';input.maxLength=1000;input.placeholder='Escribí una pregunta o mantené pulsado el micrófono...';input.setAttribute('aria-label','Pregunta al asistente');
  input.value=previous?.scope===data.scope&&previous.seed===seed?previous.value:seed;
  drafts.set(root,{scope:data.scope,seed,value:input.value});
  mic.style.touchAction='none';mic.setAttribute('aria-description','Mantené Espacio para grabar y soltá para enviar. Enter inicia o detiene la grabación. Escape cancela.');
  send.type='submit';cancel.hidden=true;form.append(input,mic,send,cancel);root.append(form,status);
  const accessible=el('details','voice-help'),summary=el('summary','','Opciones de voz y accesibilidad'),toggle=el('button','toggle','Iniciar / detener grabación');toggle.type='button';accessible.append(summary,toggle);root.append(accessible);
  let emitted=false,disposed=false;
  const emit=payload=>{if(emitted||disposed)return;emitted=true;drafts.delete(root);setTriggerValue('submission',{...payload,id:crypto.randomUUID(),scope:data.scope});};
  const sync=(state,message='')=>{
    const busy=!['IDLE','ERROR','SPEAKING'].includes(state);
    input.disabled=busy;send.disabled=busy||input.value.trim().length<3;
    mic.disabled=!data.consent||!data.hasKey||['STOPPING','TRANSCRIBING','PROCESSING'].includes(state);
    toggle.disabled=mic.disabled;cancel.hidden=!['REQUESTING_PERMISSION','RECORDING','STOPPING'].includes(state);
    mic.dataset.recording=String(state==='RECORDING');mic.setAttribute('aria-pressed',String(state==='RECORDING'));
    status.textContent=message||labels[state]||(!data.consent?'Para hablar, autorizá el micrófono y el envío a Groq en Privacidad de voz.':!data.hasKey?'Transcripción sin clave configurada. Podés escribir.':'');
  };
  const machine=new RecorderMachine({stopSpeech,getMedia:()=>navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true},video:false}),createRecorder:stream=>{const type=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));return new MediaRecorder(stream,type?{mimeType:type}:undefined);},encode:encodeAudio},sync,audio=>emit({mode:'voice',audio}));
  if(data.phase)machine.set(data.phase);else machine.set(data.error?'ERROR':'IDLE',data.error||'');
  const start=()=>{if(!data.consent||!data.hasKey||emitted)return;if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){machine.set('ERROR','El navegador no permite grabar. Usá Chrome o Edge en localhost o HTTPS.');return;}machine.start();};
  const toggleRecord=()=>{if(['REQUESTING_PERMISSION','RECORDING'].includes(machine.state))machine.stop();else start();};
  form.addEventListener('submit',e=>{e.preventDefault();const text=input.value.trim();if(send.disabled||text.length<3)return;stopSpeech();machine.set('PROCESSING');emit({mode:'text',text});},options);
  input.addEventListener('input',()=>{drafts.set(root,{scope:data.scope,seed,value:input.value});sync(machine.state);},options);
  mic.addEventListener('pointerdown',e=>{if(e.button!==0||mic.disabled)return;e.preventDefault();mic.focus();mic.setPointerCapture(e.pointerId);start();},options);
  mic.addEventListener('pointerup',()=>machine.stop(),options);
  mic.addEventListener('pointercancel',()=>machine.cancel(),options);
  mic.addEventListener('lostpointercapture',()=>{if(['REQUESTING_PERMISSION','RECORDING'].includes(machine.state))machine.cancel();},options);
  mic.addEventListener('keydown',e=>{if(e.key===' '){e.preventDefault();if(!e.repeat)start();}else if(e.key==='Enter'){e.preventDefault();if(!e.repeat)toggleRecord();}else if(e.key==='Escape')machine.cancel();},options);
  mic.addEventListener('keyup',e=>{if(e.key===' '){e.preventDefault();machine.stop();}},options);
  toggle.addEventListener('click',toggleRecord,options);cancel.addEventListener('click',()=>machine.cancel(),options);
  const interrupt=()=>{if(['REQUESTING_PERMISSION','RECORDING','STOPPING'].includes(machine.state))machine.cancel();};
  window.addEventListener('blur',interrupt,options);window.addEventListener('pagehide',interrupt,options);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)interrupt();},options);
  mic.addEventListener('blur',()=>{if(['REQUESTING_PERMISSION','RECORDING'].includes(machine.state))machine.cancel();},options);
  toggle.addEventListener('blur',()=>{if(['REQUESTING_PERMISSION','RECORDING'].includes(machine.state))machine.cancel();},options);
  return managed(()=>{disposed=true;abort.abort();machine.dispose();});
}
