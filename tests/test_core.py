import unittest
from safeguard.core import (
    SafetyExpertSystem,
    State,
    Detection,
    PersonObservation,
    decide,
    observe,
    summarize_video,
)


def d(label, box, confidence=0.9, **kwargs):
    return dict({"class": label, "bbox": box, "confidence": confidence}, **kwargs)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.expert = SafetyExpertSystem()
        # Exact boxes from the five Phase 0 counterexamples.
        self.p = d("person", [0, 100, 100, 300])
        self.h = d("helmet", [0, 100, 100, 150])
        self.v = d("vest", [0, 150, 100, 250])

    def test_audit_empty(self):
        result = self.expert.analyze([])
        self.assertEqual(result["level"], State.UNKNOWN.value)
        self.assertIsNone(result["compliance"])
        self.assertEqual(result["observations"], [])

    def test_audit_own_head(self):
        result = self.expert.analyze([self.p, self.h, self.v], 0.4, (400, 700))
        self.assertEqual(result["observations"][0]["helmet_id"], "1")
        self.assertEqual(result["observations"][0]["vest_id"], "2")
        self.assertIsNone(result["compliance"])

    def test_audit_foreign_x(self):
        result = self.expert.analyze(
            [self.p, d("helmet", [500, 100, 600, 200]), d("vest", [500, 150, 600, 250])]
        )
        self.assertIsNone(result["observations"][0]["helmet_id"])
        self.assertIsNone(result["observations"][0]["vest_id"])
        self.assertEqual(result["level"], State.UNKNOWN.value)

    def test_audit_low_conf_context(self):
        result = self.expert.analyze(
            [
                self.p,
                d("helmet", [0, 100, 100, 200], 0.1),
                d("vest", [0, 150, 100, 250], 0.1),
            ],
            0.8,
        )
        self.assertEqual(result["stats"]["helmets"], 0)
        self.assertEqual(result["stats"]["associated_pairs"], 0)
        self.assertIsNone(result["observations"][0]["helmet_id"])

    def test_audit_duplicates_never_over_100(self):
        result = self.expert.analyze([self.p, self.h, self.h, self.v, self.v])
        self.assertEqual(result["stats"]["associated_pairs"], 1)
        self.assertIsNone(result["compliance"])

    def test_shared_equipment_abstains(self):
        _, observations = observe(
            [self.p, d("worker", [20, 100, 120, 300]), d("helmet", [40, 100, 60, 130])]
        )
        self.assertTrue(all(o.ambiguous for o in observations))
        self.assertTrue(all(o.helmet_id is None for o in observations))
        self.assertTrue(all(decide(o).state == State.REVIEW for o in observations))

    def test_distinct_equipment_assigned_once(self):
        _, observations = observe(
            [
                self.p,
                self.h,
                d("person", [200, 100, 300, 300]),
                d("helmet", [220, 100, 250, 130]),
            ]
        )
        ids = [o.helmet_id for o in observations]
        self.assertEqual(len(set(ids)), 2)
        self.assertNotIn(None, ids)

    def test_occluded_abstains_even_if_reviewed(self):
        _, observations = observe([dict(self.p, occluded=True), self.h, self.v])
        self.assertEqual(
            decide(observations[0], evidence_reviewed=True).state, State.UNKNOWN
        )

    def test_border_crop_abstains(self):
        _, observations = observe([self.p, self.h, self.v], image_size=(400, 700))
        self.assertTrue(observations[0].obstructed)
        self.assertEqual(decide(observations[0]).state, State.UNKNOWN)

    def test_vertical_translation_does_not_imply_height(self):
        low = [
            d("person", [10, 300, 110, 500]),
            d("helmet", [10, 300, 110, 350]),
            d("vest", [10, 350, 110, 450]),
        ]
        high = [
            d(
                x["class"],
                [x["bbox"][0], x["bbox"][1] - 280, x["bbox"][2], x["bbox"][3] - 280],
            )
            for x in low
        ]
        a, b = [self.expert.analyze(ds, image_size=(600, 700)) for ds in (low, high)]
        self.assertEqual(a["decisions"], b["decisions"])
        self.assertEqual(a["stats"], b["stats"])
        self.assertNotIn("persons_high_risk", a["stats"])

    def test_heuristic_not_model_evidence(self):
        result = self.expert.analyze(
            [self.p, dict(self.h, inferred=True), dict(self.v, inferred=True)]
        )
        self.assertEqual(result["stats"]["helmets"], 0)
        self.assertEqual(result["stats"]["heuristic_hints"], 2)
        self.assertIsNone(result["observations"][0]["helmet_id"])
        self.assertEqual(result["level"], State.REVIEW.value)

    def test_unvalidated_positive_requires_review(self):
        result = self.expert.analyze([self.p, self.h, self.v])
        self.assertEqual(result["level"], State.REVIEW.value)

    def test_four_states_require_explicit_evidence(self):
        full = PersonObservation("p", "h", "v")
        missing = PersonObservation("p", None, "v")
        self.assertEqual(decide(full, evidence_reviewed=True).state, State.VERIFIED)
        self.assertEqual(decide(full).state, State.REVIEW)
        self.assertEqual(decide(missing).state, State.UNKNOWN)
        self.assertEqual(
            decide(missing, visible_missing=("helmet",)).state, State.UNKNOWN
        )
        self.assertEqual(
            decide(missing, evidence_reviewed=True, visible_missing=("helmet",)).state,
            State.POSSIBLE,
        )

    def test_conflicting_review_abstains(self):
        self.assertEqual(
            decide(
                PersonObservation("p", "h", "v"),
                evidence_reviewed=True,
                visible_missing=("helmet",),
            ).state,
            State.REVIEW,
        )

    def test_anatomical_region_rejects_helmet_on_feet(self):
        _, obs = observe([self.p, d("helmet", [20, 260, 50, 295])])
        self.assertIsNone(obs[0].helmet_id)

    def test_aliases_and_threshold_boundary(self):
        result = self.expert.analyze(
            [
                d(" Worker ", [0, 100, 100, 300], 0.4),
                d("HARD-HAT", [0, 100, 100, 150], 0.4),
                d("safety-vest", [0, 150, 100, 250], 0.4),
            ],
            0.4,
        )
        self.assertEqual(result["stats"]["associated_pairs"], 1)

    def test_video_descriptive_and_same_filter(self):
        frame = [d("worker", [0, 100, 100, 300]), self.h, self.v]
        result = summarize_video([frame, []])
        self.assertEqual(result["stats"]["persons"], 0.5)
        self.assertEqual(result["frames"][0], self.expert.analyze(frame))
        self.assertIsNone(result["compliance"])
        self.assertEqual(result["level"], State.UNKNOWN.value)

    def test_empty_video(self):
        result = summarize_video([])
        self.assertEqual(result["sample_count"], 0)
        self.assertIsNone(result["compliance"])

    def test_invalid_input_rejected(self):
        for confidence in (-1, 2, float("nan")):
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                Detection("0", "person", (0, 0, 1, 1), confidence)
        with self.assertRaises(ValueError):
            self.expert.analyze([d("person", [1, 1, 1, 2])])
        with self.assertRaises(ValueError):
            observe([], threshold=float("nan"))

    def test_ephemeral_ids_restart_per_image(self):
        self.assertEqual(
            self.expert.analyze([self.p])["observations"][0]["person_id"], "person-0"
        )
        self.expert.analyze([self.p, self.h, self.v])
        self.assertEqual(
            self.expert.analyze([self.p])["observations"][0]["person_id"], "person-0"
        )

    def test_detection_ids_resolve_observations(self):
        result = self.expert.analyze([self.p, self.h, self.v])
        by_id = {d["id"]: d for d in result["detections"]}
        self.assertEqual(
            by_id[result["observations"][0]["helmet_id"]]["label"], "helmet"
        )

    def test_ambiguity_does_not_depend_on_order(self):
        inputs = [
            self.p,
            d("worker", [20, 100, 120, 300]),
            d("helmet", [40, 100, 60, 130]),
        ]
        for values in (inputs, list(reversed(inputs))):
            _, observations = observe(values)
            self.assertTrue(
                all(o.ambiguous and o.helmet_id is None for o in observations)
            )


if __name__ == "__main__":
    unittest.main()
