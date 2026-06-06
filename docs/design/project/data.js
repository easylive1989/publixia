// SocialStockTracker — sample data
// People tracked + their posts. "Signal" posts carry AI-detected buy/sell calls
// and a performance object tracking the stock since the call.
//
// perf.{latest,d7,m1}: % change of the stock SINCE the call. null = still 追蹤中.
// P&L (跟單損益) is derived: long => +perf, sell/short => -perf.

window.TRACKER_DATA = (function () {
  const people = {
    ba:  { id: 'ba',  name: '巴逆逆', initial: '巴', hue: 48,  blurb: '錶圈最強分析師 · 股票其次',
           winRate: null, cumReturn: null, signals: 0, calls: 1 },
    dad: { id: 'dad', name: '爸逆逆', initial: '爸', hue: 158, blurb: '我爸已經73歲系列 · 縱橫股市30年',
           winRate: 0.31, cumReturn: -34.2, signals: 13, calls: 11 },
    aoi: { id: 'aoi', name: 'Aoi',  initial: 'A', hue: 283, blurb: '上車吃肉學 · 賣飛專家',
           winRate: 0.68, cumReturn: 22.6, signals: 7, calls: 1 },
    guc: { id: 'guc', name: '股癌',  initial: '股', hue: 2,   blurb: 'Podcast 一哥 · 嘎到財富自由',
           winRate: 0.57, cumReturn: 14.1, signals: 9, calls: 6 },
  };

  const posts = [
    {
      id: 'p1', who: 'ba', time: '3 小時前', ts: 3,
      body: '誰可以救救我\n這次至少20%回檔～ 我已經 All in 腳麻了啊啊\n看不懂的可以 google 用圖片搜尋',
      source: '看原文', signals: [],
    },
    {
      id: 'p2', who: 'ba', time: '4 小時前', ts: 4,
      body: '糟糕，龜吉有 36 dayjust',
      source: '看原文', signals: [],
    },
    {
      id: 'p3', who: 'ba', time: '13 小時前', ts: 13,
      body: '當初看上 AT 就是 dial 跟 hands 很對胃口\n結果 CW 有一個長的差不多還是一體式鏈帶的錶啊啊啊\n\n喜歡 AT，但是要砸 20 萬還是有點痛\nCW 只要 4 萬而已\n剩下的錢可以買個 Murph 38mm 或是 seiko alpinist 外加一個浪鬼',
      source: '看原文', signals: [],
    },
    {
      id: 'p4', who: 'dad', time: '18 小時前', ts: 18,
      body: '星期一是不是會有大場面？就叫大家不要 ALL IN 了。🥺',
      source: '看原文', signals: [],
    },
    {
      id: 'p5', who: 'dad', time: '19 小時前', ts: 19,
      body: '我爸已經73歲系列29\n昨天叫他停損，他說「股票放著總會回來」\n然後就去睡午覺了',
      source: '看原文', signals: [],
    },
    {
      id: 'p6', who: 'guc', time: '1 天前', ts: 30,
      body: '盤中隨手記：AI 這波拉回我自己是當作上車機會\n但不要凹單，停損該守還是要守\n下面這檔我自己有持續加碼',
      source: '看原文',
      signals: [
        { type: 'long', ticker: 'AMD', market: 'US', company: 'ADVANCED MICRO', callPrice: null,
          perf: { latest: 6.8, d7: 6.8, m1: null } },
      ],
    },
    {
      id: 'p7', who: 'guc', time: '3 天前', ts: 72, kind: 'podcast',
      title: 'EP667｜🌍 旅遊旺季與 AI 的下一棒',
      body: '歡迎收聽股癌，我是謝孟恭。本集節目由 NordVPN 贊助。六月了，夏日旅遊旺季已經展開，你是否還在猶豫旅遊規劃？現在正是時候為你的家庭旅行完成最終準備。面對貴鬆鬆的機票，不少人會透過 NordVPN 切換不同地區的 IP，比價往往有意想不到的折扣⋯⋯',
      source: '聽這集',
      signals: [
        { type: 'long', ticker: 'NVDA', market: 'US', company: 'NVIDIA CORP', callPrice: null,
          perf: { latest: -4.5, d7: null, m1: null } },
        { type: 'long', ticker: '2330', market: 'TW', company: '台積電', callPrice: null,
          perf: { latest: -2.5, d7: null, m1: null } },
      ],
    },
    {
      id: 'p8', who: 'aoi', time: '3 天前', ts: 73,
      body: '我 intc 賣在 100 也算賣飛了🥲',
      source: '看原文',
      signals: [
        { type: 'sell', ticker: 'INTC', market: 'US', company: 'INTEL CORP', callPrice: '100',
          perf: { latest: -12.0, d7: -8.4, m1: -12.0 } },
      ],
    },
    {
      id: 'p9', who: 'aoi', time: '3 天前', ts: 74,
      body: '看了一下那時候的股價 再看看現在的\n那時候也一起上車吃到肉的朋友也太幸福',
      source: '看原文', signals: [],
    },
    {
      id: 'p10', who: 'dad', time: '3 天前', ts: 75,
      body: '我爸已經73歲系列28\n縱橫股市30年總計賠掉2間房子\n\n早盤重大訊息：\n家父持股—緯創全數售出，預計轉投其他個股，有任何買賣動作會馬上通知大家。',
      source: '看原文',
      signals: [
        { type: 'sell', ticker: '3231', market: 'TW', company: '緯創', callPrice: null,
          perf: { latest: 18.4, d7: 9.1, m1: 18.4 } },
      ],
    },
    {
      id: 'p11', who: 'guc', time: '4 天前', ts: 96,
      body: '半導體設備這檔我講很久了，財報前先佈局\n反正我講完通常都會先跌一下再噴，習慣就好',
      source: '看原文',
      signals: [
        { type: 'long', ticker: '3008', market: 'TW', company: '大立光', callPrice: null,
          perf: { latest: 11.2, d7: 4.6, m1: 11.2 } },
      ],
    },
    {
      id: 'p12', who: 'dad', time: '5 天前', ts: 120,
      body: '我爸已經73歲系列27\n他今天宣布「這次真的要長期投資」\n我們上次聽到這句話是上禮拜三',
      source: '看原文',
      signals: [
        { type: 'long', ticker: '2603', market: 'TW', company: '長榮', callPrice: null,
          perf: { latest: -7.3, d7: -3.2, m1: -7.3 } },
      ],
    },
  ];

  return { people, posts };
})();
