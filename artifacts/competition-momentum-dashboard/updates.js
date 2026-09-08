window.LH180_UPDATES = {
  as_of: "2026-09-01",
  boundary: {
    changes_frozen_model: false,
    changes_ratings: false,
    replaces_sealed_ledger: false,
    partisan_polls_labeled: true
  },
  national_context: {
    range: "D+5 to D+6",
    summary: "The newest national generic-ballot releases cluster around D+5 to D+6. That supports the existing Democratic environment but does not replace the frozen D+4.8 recent-poll mean or the six-aggregator E=D+6.2 level.",
    sources: [
      { label: "Economist/YouGov · Aug 28–31 · D+6", url: "https://yougov.com/en-us/content/the-economist" },
      { label: "Reuters/Ipsos · Aug 28–31 · D+5", url: "https://www.investing.com/news/politics-news/trumps-approval-stuck-at-33-democrats-appear-more-fired-up-midtermsreutersipsos-poll-finds-4883177" }
    ]
  },
  senate: {
    Michigan: {
      point: {
        date: "2026-08-20",
        date_label: "August 10–20, 2026",
        dem_candidate: "Abdul El-Sayed",
        rep_candidate: "Mike Rogers",
        margin_dem_minus_rep: 5.0,
        pollster: "Michigan State University/YouGov",
        population: "lv",
        sample_size: 779,
        update_layer: "verified_2026_09_01"
      },
      source_label: "MSU/IPPSR official report",
      source_url: "https://ippsr.msu.edu/news/msu-poll-shows-democrats-lead-republicans-coalesce-behind-rogers",
      note: "D+5 among likely voters and D+4 among registered voters. This extends the late-August Democratic lead but does not show a new acceleration."
    },
    Iowa: {
      point: {
        date: "2026-08-29",
        date_label: "August 27–29, 2026",
        dem_candidate: "Josh Turek",
        rep_candidate: "Ashley Hinson",
        margin_dem_minus_rep: -2.0,
        pollster: "Wedgewood",
        population: "lv",
        sample_size: 600,
        update_layer: "verified_2026_09_01"
      },
      source_label: "Iowa poll listing",
      source_url: "https://www.270towin.com/2026-senate-polls/iowa",
      note: "R+2 is less Republican than the preceding R+3 and R+4 polls. The registered two-window shift remains toward Republicans at about 3.5 points, but the latest point softens rather than accelerates it."
    }
  },
  house: {
    "MI-10": {
      status: "supports_tossup",
      headline: "New district poll: tied 45–45",
      detail: "A Democratic-sponsored GSG/HMP poll has Christina Hines and Michael Bouchard Jr. tied. It supports the current Tossup classification, but one sponsored poll does not establish momentum.",
      source_label: "House Majority PAC release · Aug 31",
      source_url: "https://www.thehousemajoritypac.com/news/hmp-poll-christina-hines-tied-with-michael-bouchard-junior-in-mi-10"
    },
    "FL-13": {
      status: "partisan_conflict",
      headline: "Partisan internals conflict: D+5 versus R+8",
      detail: "A Democratic-sponsored Hart/HMP poll has Leela Gray ahead by 5, while an earlier Republican-sponsored Fabrizio poll had Anna Paulina Luna ahead by 8. The 13-point sponsor spread is evidence of competitiveness, not a rating change; Lean R is retained.",
      source_label: "House Majority PAC release · Sep 1",
      source_url: "https://www.thehousemajoritypac.com/news/hmp-poll-leela-gray-leads-anna-paulina-luna-in-fl-13"
    }
  }
};
