import test from 'node:test';
import assert from 'node:assert/strict';
import mount,{RecorderMachine,pcmWav,shouldAutoPlay,chooseVoice} from '../safeguard/copilot/audio_component.mjs';

function setup({pending=false,reject=false}={}) {
  let resolve,closed=0,sent=0,encoded=0;
  const track={stop(){closed++;}},stream={getTracks:()=>[track]};
  const recorder={state:'inactive',mimeType:'audio/webm',start(){this.state='recording';},stop(){this.state='inactive';this.ondataavailable?.({data:{size:10}});this.onstop?.();}};
  const states=[];
  const api={getMedia:()=>reject?Promise.reject(Error('denied')):pending?new Promise(r=>{resolve=r;}):Promise.resolve(stream),createRecorder:()=>recorder,stopSpeech(){},encode:async()=>{encoded++;return 'audio';}};
  const machine=new RecorderMachine(api,s=>states.push(s),()=>sent++);
  return {machine,stream,recorder,states,resolve:()=>resolve(stream),stats:()=>({closed,sent,encoded})};
}
const tick=()=>new Promise(r=>setImmediate(r));
test('press and release submit exactly once; tracks close',async()=>{const x=setup();await x.machine.start();assert.equal(x.machine.state,'RECORDING');x.machine.stop();x.machine.stop();await tick();assert.equal(x.stats().sent,1);assert.ok(x.stats().closed>0);assert.equal(x.machine.state,'TRANSCRIBING');x.machine.dispose();});
test('release before permission never starts recorder',async()=>{const x=setup({pending:true});const p=x.machine.start();x.machine.stop();x.resolve();await p;assert.equal(x.recorder.state,'inactive');assert.equal(x.stats().sent,0);assert.equal(x.stats().closed,1);x.machine.dispose();});
test('permission denial is recoverable',async()=>{const x=setup({reject:true});await x.machine.start();assert.equal(x.machine.state,'ERROR');assert.equal(x.stats().sent,0);x.machine.dispose();});
test('cancel while awaiting permission releases late stream',async()=>{const x=setup({pending:true});const p=x.machine.start();x.machine.cancel();x.resolve();await p;assert.equal(x.stats().sent,0);assert.equal(x.stats().closed,1);x.machine.dispose();});
test('pointer cancel / focus loss cancellation never submits',async()=>{const x=setup();await x.machine.start();x.machine.cancel();await tick();assert.equal(x.stats().sent,0);assert.equal(x.recorder.state,'inactive');x.machine.dispose();});
test('unmount during permission cannot leak microphone',async()=>{const x=setup({pending:true});const p=x.machine.start();x.machine.dispose();x.resolve();await p;assert.equal(x.stats().closed,1);assert.equal(x.stats().sent,0);});
test('unmount during recording cancels before encode',async()=>{const x=setup();await x.machine.start();x.machine.dispose();await tick();assert.equal(x.stats().sent,0);assert.equal(x.stats().encoded,0);});
test('late encoder resolution after cancellation does not submit',async()=>{const x=setup();let resolve;x.machine.api.encode=()=>new Promise(r=>resolve=r);await x.machine.start();x.machine.stop();x.machine.cancel();resolve('audio');await tick();assert.equal(x.stats().sent,0);x.machine.dispose();});
test('PCM WAV is actual mono 16k 16bit audio',()=>{const bytes=pcmWav(new Float32Array([-.5,0,.5]));const view=new DataView(bytes.buffer);assert.equal(new TextDecoder().decode(bytes.slice(0,4)),'RIFF');assert.equal(view.getUint16(22,true),1);assert.equal(view.getUint32(24,true),16000);assert.equal(view.getUint32(40,true),6);});
test('voice auto once, text never auto, another voice message allowed',()=>{const seen=new Set();assert.equal(shouldAutoPlay('text','a',seen),false);assert.equal(shouldAutoPlay('voice','b',seen),true);assert.equal(shouldAutoPlay('voice','b',seen),false);assert.equal(shouldAutoPlay('voice','c',seen),true);});
test('prefer local es-AR; exclude remote speech services',()=>{const remote={lang:'es-AR',localService:false},es={lang:'es-ES',localService:true},ar={lang:'es-AR',localService:true};assert.equal(chooseVoice([remote,es,ar]),ar);assert.equal(chooseVoice([remote,es]),es);assert.equal(chooseVoice([remote]),undefined);});

class Element extends EventTarget {
  constructor(tag='div'){super();this.tag=tag;this.children=[];this.style={};this.dataset={};this.value='';this.attributes={};}
  append(...items){for(const item of items)item.parent=this;this.children.push(...items);}
  get tagName(){return this.tag.toUpperCase();}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
  setAttribute(k,v){this.attributes[k]=v;}
  set innerHTML(value){this.children=[];this.html=value;}
  focus(){}
  setPointerCapture(){}
}
test('component updates preserve Streamlit injected styles',()=>{
  browserMock();const root=new Element(),style=new Element('div');style.append(new Element('style'));root.append(style);
  const data={kind:'composer',scope:'styles'};
  mount({parentElement:root,data});
  const cleanup=mount({parentElement:root,data});
  assert.equal(root.children[0],style);
  assert.equal(root.children.filter(x=>x.tag==='form').length,1);cleanup();
});
function browserMock(){
  const calls={speak:0,pause:0,resume:0,cancel:0};let utterance;
  globalThis.document=new EventTarget();document.createElement=tag=>new Element(tag);
  globalThis.window=new EventTarget();
  globalThis.SpeechSynthesisUtterance=class{constructor(text){this.text=text;}};
  window.SpeechSynthesisUtterance=globalThis.SpeechSynthesisUtterance;
  window.speechSynthesis={getVoices:()=>[{name:'Español local',lang:'es-AR',localService:true}],speak:u=>{calls.speak++;utterance=u;u.onstart();},cancel:()=>calls.cancel++,pause:()=>calls.pause++,resume:()=>calls.resume++};
  return {calls,last:()=>utterance};
}
test('text response is silent; manual listen, pause, resume and stop',()=>{
  const b=browserMock(),root=new Element();const cleanup=mount({parentElement:root,data:{kind:'player',text:'Respuesta validada.',id:'manual',mode:'text'}});
  assert.equal(b.calls.speak,0);const [speak,pause,resume,stop]=root.children[0].children;
  speak.dispatchEvent(new Event('click'));assert.equal(b.calls.speak,1);assert.equal(b.last().text,'Respuesta validada.');assert.equal(pause.hidden,false);
  pause.dispatchEvent(new Event('click'));assert.equal(b.calls.pause,1);assert.equal(resume.hidden,false);
  resume.dispatchEvent(new Event('click'));assert.equal(b.calls.resume,1);
  stop.dispatchEvent(new Event('click'));assert.equal(speak.hidden,false);assert.ok(b.calls.cancel>0);cleanup();
});
test('voice response auto speaks once across reruns; cleanup cancels',()=>{
  const b=browserMock(),data={kind:'player',text:'Respuesta validada.',id:'autoplay-rerun',mode:'voice'};
  const cleanup=mount({parentElement:new Element(),data});assert.equal(b.calls.speak,1);cleanup();
  const cleanup2=mount({parentElement:new Element(),data});assert.equal(b.calls.speak,1);assert.ok(b.calls.cancel>0);cleanup2();
});
test('another response stops previous speech; error exposes manual control',()=>{
  const b=browserMock(),a=new Element(),c=new Element();const cleanA=mount({parentElement:a,data:{kind:'player',text:'A',id:'a-manual',mode:'text'}});
  a.children[0].children[0].dispatchEvent(new Event('click'));const prior=b.calls.cancel;
  const cleanC=mount({parentElement:c,data:{kind:'player',text:'C',id:'c-manual',mode:'text'}});
  c.children[0].children[0].dispatchEvent(new Event('click'));assert.ok(b.calls.cancel>prior);
  b.last().onerror();assert.equal(c.children[0].children[0].hidden,false);assert.match(c.children[1].textContent,/Escuchar respuesta/);cleanA();cleanC();
});
test('no local Spanish voice does not call remote TTS',()=>{
  const b=browserMock();window.speechSynthesis.getVoices=()=>[{lang:'es-AR',localService:false}];const root=new Element();
  const cleanup=mount({parentElement:root,data:{kind:'player',text:'Hola',id:'no-voice',mode:'voice'}});
  assert.equal(b.calls.speak,0);assert.match(root.children[1].textContent,/voz española local/);cleanup();
});
test('composer submits once, disables empty send and retains draft across updates',()=>{
  browserMock();const root=new Element(),events=[],data={kind:'composer',scope:'one',consent:false,hasKey:false};
  let cleanup=mount({parentElement:root,data,setTriggerValue:(k,v)=>events.push(v)});
  let form=root.children[0],input=form.children[0];assert.equal(form.children[2].disabled,true);
  input.value='Consulta pendiente';input.dispatchEvent(new Event('input'));assert.equal(form.children[2].disabled,false);
  cleanup=mount({parentElement:root,data,setTriggerValue:(k,v)=>events.push(v)});
  form=root.children[0];assert.equal(form.children[0].value,'Consulta pendiente');
  form.dispatchEvent(new Event('submit',{cancelable:true}));form.dispatchEvent(new Event('submit',{cancelable:true}));
  assert.equal(events.length,1);assert.equal(events[0].mode,'text');assert.equal(events[0].scope,'one');cleanup();
});
test('scope change discards draft; composer update does not cancel another player',()=>{
  const b=browserMock(),root=new Element(),playerRoot=new Element();
  const playerCleanup=mount({parentElement:playerRoot,data:{kind:'player',id:'survive-composer',mode:'text',text:'Respuesta'}});
  playerRoot.children[0].children[0].dispatchEvent(new Event('click'));const prior=b.calls.cancel;
  let cleanup=mount({parentElement:root,data:{kind:'composer',scope:'one'}});
  root.children[0].children[0].value='Borrador';root.children[0].children[0].dispatchEvent(new Event('input'));
  cleanup=mount({parentElement:root,data:{kind:'composer',scope:'two'}});
  assert.equal(root.children[0].children[0].value,'');assert.equal(b.calls.cancel,prior);cleanup();playerCleanup();
});
