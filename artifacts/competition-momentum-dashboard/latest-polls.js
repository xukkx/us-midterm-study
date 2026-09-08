window.LH216_LATEST_POLLS = {
  as_of: "2026-09-03",
  checked_at: "2026-09-03T15:45:14-04:00",
  scope: "截至核验时点、且未进入 LH-169 冻结账本或 LH-180 增量层的公开正式对阵民调",
  boundary: {
    changes_frozen_data: false,
    changes_registered_momentum: false,
    changes_ratings: false,
    changes_model_parameters: false,
    replaces_sealed_ledger: false,
    partisan_polls_labeled: true,
    forecasts_excluded: true,
    issue_only_polls_excluded: true
  },
  national_context: {
    raw_poll_status: "未发现晚于 8 月 31 日结束访谈的新全国 generic-ballot 原始样本",
    latest_raw_range: "D+5 至 D+6",
    aggregate_snapshot: "Silver Bulletin 9 月 2 日快照为 D+6.6",
    summary: "最新原始全国样本仍是 Economist/YouGov 与 Reuters/Ipsos 的 8 月 28–31 日调查；Silver 的 D+6.6 只是当日聚合快照，不回写冻结 E=D+6.2，也不重算众院点位。",
    sources: [
      { label: "Silver Bulletin · 9 月 2 日 · 聚合 D+6.6", url: "https://www.natesilver.net/p/generic-ballot-average-2026-nate-silver-bulletin-congress-polls" },
      { label: "Economist/YouGov · 8 月 28–31 日 · D+6", url: "https://yougov.com/en-us/content/the-economist" },
      { label: "Reuters/Ipsos · 8 月 28–31 日 · D+5", url: "https://www.investing.com/news/politics-news/trumps-approval-stuck-at-33-democrats-appear-more-fired-up-midtermsreutersipsos-poll-finds-4883177" }
    ]
  },
  senate: {
    Iowa: {
      points: [
        {
          date: "2026-08-28",
          date_label: "2026 年 8 月 26–28 日",
          release_date: "2026-09-02",
          dem_candidate: "Josh Turek",
          rep_candidate: "Ashley Hinson",
          dem_share: 52,
          rep_share: 46,
          margin_dem_minus_rep: 6,
          pollster: "Abacus Data",
          population: "rv",
          sample_size: 500,
          moe: "未给出；在线非概率样本",
          sponsor: "Abacus Data 自费",
          partisan_sponsorship: "未发现党派或候选人赞助",
          source_label: "Abacus Data 五州调查 · 官方发布",
          source_url: "https://abacusdata.ca/the-trade-war-next-door-what-american-voters-think-about-tariffs-canada-and-the-battle-for-the-u-s-senate/",
          update_layer: "verified_2026_09_03"
        },
        {
          date: "2026-09-01",
          date_label: "2026 年 8 月 31 日–9 月 1 日",
          release_date: "2026-09-03",
          dem_candidate: "Josh Turek",
          rep_candidate: "Ashley Hinson",
          dem_share: 45,
          rep_share: 50,
          margin_dem_minus_rep: -5,
          pollster: "Emerson College Polling",
          population: "lv",
          sample_size: 750,
          moe: "±3.6pp 可信区间",
          sponsor: "Nexstar Media",
          partisan_sponsorship: "非党派媒体赞助",
          source_label: "Emerson College Polling · 官方发布",
          source_url: "https://emersoncollegepolling.com/iowa-2026-poll-hinson-leads-turek/",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "insufficient",
        headline: "最新 R+5；同期机构分歧达 11pp",
        status: "不改写冻结动量",
        level: "Abacus D+6 RV · Wedgewood R+2 LV · Emerson R+5 LV",
        summary: "三份相邻调查从 D+6 到 R+5，机构与投票人群口径差异大于时间变化。冻结两窗判读仍保留为原始记录；当前展示不把这组冲突样本写成新的确定动量。"
      }
    },
    Texas: {
      points: [
        {
          date: "2026-08-26",
          date_label: "2026 年 8 月 24–26 日",
          release_date: "未在发布页标明",
          dem_candidate: "James Talarico",
          rep_candidate: "Ken Paxton",
          dem_share: 50,
          rep_share: 50,
          margin_dem_minus_rep: 0,
          pollster: "Overton Insights",
          population: "lv",
          sample_size: 1167,
          moe: "±2.9pp",
          sponsor: "发布页未披露",
          partisan_sponsorship: "发布页未披露；聚合源将机构标为 R",
          question_variant: "含倾向者；初始选择为 Talarico 44.0%、Paxton 43.4%",
          source_label: "Overton Insights · 官方发布",
          source_url: "https://overtoninsights.com/poll/september-2026/",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "toward_D",
        headline: "较春季向 D；最新含倾向者为平手",
        status: "多机构确认当前竞争",
        level: "TPOR D+6 · Overton 平手",
        summary: "8 月后段两项调查仍比春季多数读数更偏民主党，但最新 Overton 的含倾向者口径为 50–50。保留原先“自春季向 D、近期趋稳”的复核结论，不声称继续加速。"
      }
    },
    Michigan: {
      points: [
        {
          date: "2026-08-28",
          date_label: "2026 年 8 月 22–28 日",
          release_date: "2026-08-29",
          dem_candidate: "Abdul El-Sayed",
          rep_candidate: "Mike Rogers",
          dem_share: 47,
          rep_share: 43,
          margin_dem_minus_rep: 4,
          pollster: "EPIC-MRA",
          population: "lv",
          sample_size: 600,
          moe: "±4.0pp",
          sponsor: "发布文件未标明党派赞助",
          partisan_sponsorship: "未发现党派或候选人赞助",
          source_label: "EPIC-MRA 频数报告",
          source_url: "https://data.ddhq.io/polls/2026/08/29/EPIC-MRA-Michigan",
          update_layer: "verified_2026_09_03"
        },
        {
          date: "2026-08-28",
          date_label: "2026 年 8 月 26–28 日",
          release_date: "2026-09-02",
          dem_candidate: "Abdul El-Sayed",
          rep_candidate: "Mike Rogers",
          dem_share: 48,
          rep_share: 41,
          margin_dem_minus_rep: 6,
          reported_margin_note: "发布方以未四舍五入值报告 El-Sayed +6；页面整数份额相差 7pp",
          pollster: "Abacus Data",
          population: "rv",
          sample_size: 500,
          moe: "未给出；在线非概率样本",
          sponsor: "Abacus Data 自费",
          partisan_sponsorship: "未发现党派或候选人赞助",
          source_label: "Abacus Data 五州调查 · 官方发布",
          source_url: "https://abacusdata.ca/the-trade-war-next-door-what-american-voters-think-about-tariffs-canada-and-the-battle-for-the-u-s-senate/",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "toward_D",
        headline: "三家后段样本均给出 D+4 至 D+6",
        status: "跨机构确认当前领先",
        level: "EPIC D+4 LV · MSU D+5 LV · Abacus 报告 D+6 RV",
        summary: "三家不同机构均显示 El-Sayed 小幅领先，确认当前民主党优势；这些相邻时间点集中在同一范围，不构成新的加速度证据。"
      }
    },
    "Ohio (special)": {
      points: [
        {
          date: "2026-08-28",
          date_label: "2026 年 8 月 26–28 日",
          release_date: "2026-09-02",
          dem_candidate: "Sherrod Brown",
          rep_candidate: "Jon Husted",
          dem_share: 53,
          rep_share: 43,
          margin_dem_minus_rep: 10,
          pollster: "Abacus Data",
          population: "rv",
          sample_size: 500,
          moe: "未给出；在线非概率样本",
          sponsor: "Abacus Data 自费",
          partisan_sponsorship: "未发现党派或候选人赞助",
          source_label: "Abacus Data 五州调查 · 官方发布",
          source_url: "https://abacusdata.ca/the-trade-war-next-door-what-american-voters-think-about-tariffs-canada-and-the-battle-for-the-u-s-senate/",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "insufficient",
        headline: "新项 D+10；机构序列仍不支持单一动量",
        status: "水平可读、动量冲突",
        level: "Abacus D+10 RV · 8 月既有 D+4 至 D+8",
        summary: "新样本强化 Brown 当前领先的可能性，但与先前 NYT 的 R+3 等读数仍有明显机构差；不据单项高值替换冻结的预注册判断。"
      }
    },
    Maine: {
      points: [
        {
          date: "2026-08-28",
          date_label: "2026 年 8 月 26–28 日",
          release_date: "2026-09-02",
          dem_candidate: "Troy Jackson",
          rep_candidate: "Susan Collins",
          dem_share: 45,
          rep_share: 46,
          margin_dem_minus_rep: -1,
          pollster: "Abacus Data",
          population: "rv",
          sample_size: 500,
          moe: "未给出；在线非概率样本",
          sponsor: "Abacus Data 自费",
          partisan_sponsorship: "未发现党派或候选人赞助",
          source_label: "Abacus Data 五州调查 · 官方发布",
          source_url: "https://abacusdata.ca/the-trade-war-next-door-what-american-voters-think-about-tariffs-canada-and-the-battle-for-the-u-s-senate/",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "insufficient",
        headline: "同一调查对投票人群筛选高度敏感",
        status: "不作动量判断",
        level: "Abacus RV R+1；LV 子样本 D+9",
        summary: "Abacus 的全州 500 名注册选民读数为 Collins 46–45，但其较小的可能投票者子样本为 Jackson 52–43。筛选口径可令方向翻转，因此只登记 RV 正式点并公开敏感性，不声称新动量。"
      }
    },
    "South Carolina": {
      points: [
        {
          date: "2026-08-28",
          date_label: "2026 年 8 月 26–28 日",
          release_date: "2026-09-02",
          dem_candidate: "Annie Andrews",
          rep_candidate: "Darline Graham Nordone",
          dem_share: 48,
          rep_share: 47,
          margin_dem_minus_rep: 1,
          pollster: "Abacus Data",
          population: "rv",
          sample_size: 500,
          moe: "未给出；在线非概率样本",
          sponsor: "Abacus Data 自费",
          partisan_sponsorship: "未发现党派或候选人赞助",
          source_label: "Abacus Data 五州调查 · 官方发布",
          source_url: "https://abacusdata.ca/the-trade-war-next-door-what-american-voters-think-about-tariffs-canada-and-the-battle-for-the-u-s-senate/",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "insufficient",
        headline: "RV 近乎平手；LV 子样本明显偏 R",
        status: "口径敏感",
        level: "Abacus RV D+1；LV 子样本 R+13",
        summary: "同一调查的注册选民与可能投票者筛选给出截然不同的边际；连同既有 Impact 平手，只能说明人群口径重要，不能据此登记确定动量。"
      }
    },
    "New Hampshire": {
      points: [
        {
          date: "2026-08-24",
          date_label: "2026 年 8 月 20–24 日",
          release_date: "2026-08-26",
          dem_candidate: "Chris Pappas",
          rep_candidate: "John E. Sununu",
          dem_share: 43,
          rep_share: 45,
          margin_dem_minus_rep: -2,
          pollster: "University of New Hampshire Survey Center",
          population: "lv",
          sample_size: 1878,
          moe: "±2.3pp",
          sponsor: "Granite State Poll",
          partisan_sponsorship: "未发现党派或候选人赞助",
          source_label: "UNH Survey Center · 官方发布",
          source_url: "https://scholars.unh.edu/survey_center_polls/988/",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "insufficient",
        headline: "UNH R+2；St. Anselm D+7",
        status: "机构序列冲突",
        level: "同期读数相差 9pp",
        summary: "UNH 从年初 D+5 走到 R+2，而 St. Anselm 同期给出 D+7。两条高频序列方向相反，不能合成为新的州级动量。"
      }
    },
    Minnesota: {
      points: [
        {
          date: "2026-08-17",
          date_label: "2026 年 8 月 13–17 日",
          release_date: "2026-08-18",
          dem_candidate: "Peggy Flanagan",
          rep_candidate: "Michele Tafoya",
          dem_share: 46,
          rep_share: 41,
          margin_dem_minus_rep: 5,
          pollster: "SurveyUSA",
          population: "lv",
          sample_size: 661,
          moe: "±4.3pp",
          sponsor: "KSTP/KAAL/WDIO",
          partisan_sponsorship: "非党派媒体赞助",
          source_label: "270toWin · SurveyUSA 原发布索引",
          source_url: "https://www.270towin.com/2026-senate-polls/minnesota",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "flat",
        headline: "两项 8 月样本均为 D+5",
        status: "水平获确认",
        level: "SurveyUSA D+5 · Deep Root D+5",
        summary: "不同机构在相邻日期给出相同边际，支持当前民主党领先约 5pp；缺少更长的同对阵时间序列，不能登记新的方向变化。"
      }
    },
    "New Mexico": {
      points: [
        {
          date: "2026-08-28",
          date_label: "2026 年 8 月 21–28 日",
          release_date: "2026-09-01",
          dem_candidate: "Ben Ray Luján",
          rep_candidate: "Larry Marker",
          dem_share: 53,
          rep_share: 38,
          margin_dem_minus_rep: 15,
          pollster: "Research & Polling Inc.",
          population: "lv",
          sample_size: 516,
          moe: "±4.3pp",
          sponsor: "Albuquerque Journal",
          partisan_sponsorship: "非党派媒体赞助",
          source_label: "KOAT · Albuquerque Journal 调查报道",
          source_url: "https://www.koat.com/article/albuquerque-journal-poll-shows-lujan-leading-marker-in-us-senate-race/73579329",
          update_layer: "verified_2026_09_03"
        }
      ],
      crosscheck: {
        momentum: "insufficient",
        headline: "首项正式对阵为 D+15",
        status: "单项证据",
        level: "Research & Polling D+15 LV",
        summary: "这是冻结账本之后首项可核验正式对阵，只能说明当前水平；一份调查不能形成时间趋势。"
      }
    }
  },
  house: {
    "TX-35": {
      status: "single_partisan_poll",
      headline: "新选区民调：Garcia 44–De La Cruz 45",
      detail: "Normington Petts 为 House Majority PAC 所做的 500 名可能投票者调查显示 R+1，属于统计范围内的接近竞逐。该调查由民主党阵营赞助，只作单项地区证据，不改变冻结 Tossup 评级或模型位置。",
      date_label: "2026 年 8 月 27–31 日",
      release_date: "2026-09-02",
      pollster: "Normington Petts",
      population: "lv",
      sample_size: 500,
      margin_dem_minus_rep: -1,
      sponsor: "House Majority PAC",
      partisan_sponsorship: "民主党阵营赞助",
      source_label: "House Majority PAC · 9 月 2 日发布",
      source_url: "https://www.thehousemajoritypac.com/news/hmp-poll-johnny-garcia-statistically-tied-with-carlos-de-la-cruz-in-tx-35"
    }
  },
  exclusions: [
    {
      item: "Decision Desk HQ 9 月 1 日 TX/OH 数字",
      reason: "为模型/预测输出，缺少民调样本与方法，不作为原始民调点"
    },
    {
      item: "CO-08 Latino Policy Agenda 9 月 1 日发布",
      reason: "只测总统/议员观感，未提供本仪表盘所需的正式众院候选人对阵"
    }
  ]
};
