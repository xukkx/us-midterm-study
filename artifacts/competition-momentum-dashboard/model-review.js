window.LH_MODEL_REVIEW = {
  as_of: "2026-09-03",
  base_data_as_of: "2026-08-31",
  latest_evidence_as_of: "2026-09-01",
  status: "NO LIVE MODEL REPLACEMENT",
  summary: "Later frozen audits improve the explanation of model risk, but none authorizes a new public 2026 mapping. The live dashboard therefore keeps its existing readings and labels the House map as provisional context.",
  layers: [
    {
      id: "house_live",
      label: "House · live context layer",
      headline: "Cumulative level and four-week momentum remain separate",
      detail: "The displayed House level still uses PVI plus 1.3308 × (E − 0.977); the four-week signal uses 1.3308 × the change in the generic ballot. LH-178 found the 0.977 center has unresolved lineage and the coefficient came from a cross-chamber path, so the mapped level is context-only, not a validated forecast.",
      evidence: "LH-178 · CONTEXT_ONLY_UNVALIDATED_CROSS_CHAMBER_MAPPING"
    },
    {
      id: "house_shadow",
      label: "House · shadow challenger",
      headline: "A simpler coefficient looks better, but is not yet decisive",
      detail: "Across the three archived cycles and every tested horizon, c=0.5 had the lowest MAE. At 60 days its equal-cycle MAE was 5.849 versus 6.346 for the deployed map, but the 90% interval for the difference still crossed zero. LH-179 therefore authorizes continued shadowing only.",
      evidence: "LH-179 · experimental_archival_three_cycles"
    },
    {
      id: "candidate_resources",
      label: "House · candidate and resources",
      headline: "Historical signal exists; it is not in the live map",
      detail: "The candidate-field and resource layers reduced historical equal-cycle MAE from 6.836 to 5.961 across three forward folds. The finance snapshots were not standardized to one as-of date and there are too few independent cycles, so LH-181 does not authorize a 2026 adjustment.",
      evidence: "LH-181 · experimental_historical"
    },
    {
      id: "senate_diagnostic",
      label: "Senate · candidate structure",
      headline: "Promising post-hoc diagnostic, no public promotion",
      detail: "The pre-registered ballot-history challengers failed their gate. A later centered, zero-sum diagnostic reduced MAE, but it was triggered by that failure and was not an independent test. LH-182/LH-183 therefore leave Senate cards on polling, PVI context and descriptive ratings.",
      evidence: "LH-182/LH-183 · post_result_exploratory_diagnostic"
    }
  ],
  boundary: {
    changes_frozen_data: false,
    changes_live_parameters: false,
    changes_ratings: false,
    public_replacement_authorized: false,
    probabilities_emitted: false
  }
};
