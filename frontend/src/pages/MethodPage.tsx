import { Link } from 'react-router-dom';
import { HEAT_LEVELS, HEAT_META } from '@/lib/market-heat';

/** 計算原理說明頁：把「冷熱判讀」四個步驟攤開，讓數字可被複現。 */
export default function MethodPage() {
  return (
    <main className="wrap doc">
      <div className="toolbar">
        <Link className="method-link" to="/">← 回判讀</Link>
      </div>

      <h1>計算原理</h1>
      <p className="lede">
        「大盤成交金額冷熱判讀」要回答的是一件事：<strong>今天的量能，相對於現在的指數位階，
        算多還是算少？</strong>下面是從原始資料到五級判讀的完整推導——先以台股為例，
        <a href="#nasdaq">同一套原則怎麼套用在 Nasdaq</a> 寫在後面。
      </p>

      <h2>為什麼不能直接看成交金額</h2>
      <p>
        一萬億的成交金額，在指數三萬點時是天量，在四萬五千點時卻可能是地量。台股的量能隨指數
        <strong>超線性</strong>成長——實際擬合出的彈性約 <span className="mono">1.6</span>，
        意思是指數上漲 10%，合理的量能會上漲約 16%。
      </p>
      <p>
        所以「近月均量」這類固定基準會系統性地誤判：多頭走高時把每天都讀成偏熱，回檔時又把每天
        讀成偏冷。要判斷冷熱，得先把「指數位階」這個因素折算掉。
      </p>

      <h2>四個步驟</h2>

      <section className="step">
        <h3><span className="step-n">1</span>位階常態 — 這個指數位階「該有」多少量</h3>
        <p>
          取全歷史每個交易日，對量能與指數同取自然對數後做最小平方迴歸：
        </p>
        <pre className="formula">ln(量能) = a + b × ln(指數)</pre>
        <p>
          擬合出 <span className="mono">a</span>、<span className="mono">b</span> 後，把當天的指數
          代回去，就得到當天的<strong>位階常態</strong>——在這個位階下，統計上「應該」出現的成交金額：
        </p>
        <pre className="formula">位階常態 = exp(a + b × ln(加權指數))</pre>
        <p className="note">
          這就是主圖上那條<strong>灰色虛線</strong>。它隨指數起伏，不是一條水平的均量線。
        </p>
      </section>

      <section className="step">
        <h3><span className="step-n">2</span>量能比與殘差 — 實際偏離常態多少</h3>
        <pre className="formula">量能比 = 成交金額 ÷ 位階常態{'\n'}殘差　 = ln(量能比)</pre>
        <p>
          量能比 <span className="mono">1.20</span> 表示當天量能比該位階的常態多兩成。取對數轉成
          <strong>殘差</strong>，是為了讓「多兩成」和「少兩成」在數線上對稱等距，才適合拿來排名。
        </p>
      </section>

      <section className="step">
        <h3><span className="step-n">3</span>近一年百分位 — 這個偏離在近期算不算極端</h3>
        <p>
          偏離多少是「多」，沒有絕對標準，得看近期的分佈。把當天的殘差放進<strong>最近 240 個
          交易日（約一年）</strong>的殘差集合裡排名，取百分位（等同試算表的
          <span className="mono"> PERCENTRANK.INC</span>）：
        </p>
        <pre className="formula">近一年百分位 = 近一年中殘差低於今天的天數 ÷ (樣本數 − 1)</pre>
        <p className="note">
          因為是<strong>相對排名</strong>，在一段整體低迷的期間裡，一個量能比仍小於 1 的日子，
          也可能因為排進前段而被判為偏熱——這是相對冷熱，不是絕對量能。
        </p>
      </section>

      <section className="step">
        <h3><span className="step-n">4</span>五級判讀</h3>
        <p>百分位落在哪一段，就是當天的判讀：</p>
        <table className="band-table">
          <thead>
            <tr><th>近一年百分位</th><th>判讀</th></tr>
          </thead>
          <tbody>
            {[
              { lv: 'very_hot', range: '≥ 0.8' },
              { lv: 'hot', range: '0.6 – 0.8' },
              { lv: 'normal', range: '0.4 – 0.6' },
              { lv: 'cold', range: '0.2 – 0.4' },
              { lv: 'very_cold', range: '≤ 0.2' },
            ].map(({ lv, range }) => {
              const meta = HEAT_META[lv as (typeof HEAT_LEVELS)[number]];
              return (
                <tr key={lv}>
                  <td className="mono">{range}</td>
                  <td>
                    <span
                      className="sheet-verdict"
                      style={{ background: meta.color, color: meta.darkText ? 'var(--ink)' : '#fff' }}
                    >
                      {meta.zh}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <h2>怎麼看兩張圖</h2>
      <ul>
        <li>
          <strong>成交金額圖</strong>：長條是實際成交金額，虛線是位階常態。長條高過虛線＝量能超出
          常態，低於虛線＝量能不足。長條顏色是該日的判讀。
        </li>
        <li>
          <strong>大盤位階圖</strong>：灰線是加權指數走勢（只表示位階），每個點的顏色是當天的判讀。
          用來看「指數在漲的時候，量能到底有沒有跟上」。
        </li>
      </ul>

      <h2 id="nasdaq">套用在 Nasdaq</h2>
      <p>
        上面四個步驟一個字都沒改就搬到美股了——判讀模型本身跟市場無關，它只吃「指數收盤 ＋
        當日量能」，每個市場各自用<strong>自己的歷史</strong>迴歸、<strong>自己的近一年分佈</strong>
        排百分位。兩邊的數字不互相比較，只跟自己的位階常態比。
      </p>
      <p>
        配的是 <strong>Nasdaq Composite 指數 ＋ Nasdaq 上市股票的 composite volume</strong>。挑這一
        組是因為指數與量能<strong>來自同一個宇宙</strong>：美股的成交量是碎的（NYSE / Nasdaq /
        Cboe / IEX 再加上約四成 off-exchange），「全市場成交量」不是一個現成數字，拿 S&P 500 去配
        全市場量等於在比兩個不同的東西。
      </p>

      <h3>量能用的是成交股數，不是成交金額</h3>
      <p>
        美股沒有免費而穩定的「全市場成交金額」日資料源，而 composite volume 在美股語境裡本來就是
        指股數。這對判讀的影響比直覺小：
      </p>
      <pre className="formula">ln(成交金額) ≈ ln(成交股數) + ln(成交均價)</pre>
      <p>
        成交均價大致隨指數等比例走，所以把 ln(量) 對 ln(指數) 迴歸時，用股數只是把擬合斜率整體平移
        約 1，<strong>殘差——也就是判讀真正吃的東西——幾乎不變</strong>。差別只在圖上那條位階常態的
        斜度。
      </p>

      <h3>看 Nasdaq 判讀時要留意的三件事</h3>
      <ul>
        <li>
          <strong>「偏熱」的語意會反過來。</strong>台股放量多半伴隨散戶追價，「量大＝過熱」的直覺
          站得住；美股相當大比例是被動、演算法與再平衡流量，<strong>放量最常出現在恐慌下殺</strong>
          而非狂熱。同一個 PR 90，在台股偏向「過熱該小心」，在美股可能是「剛崩完」。判讀請和
          大盤位階圖上的指數走勢一起看。
        </li>
        <li>
          <strong>制度性巨量日會被無條件讀成明顯偏熱。</strong>四巫日（3/6/9/12 月第三個週五）、
          Russell 重組（6 月）、月底再平衡，這些日子的量能是行事曆決定的，不是情緒。
        </li>
        <li>
          <strong>半日盤必然讀成明顯偏冷。</strong>感恩節隔天、聖誕夜、7 月 3 日只交易半天，
          量能自然腰斬。這是真實資料，不是錯誤，但別當成情緒訊號。
        </li>
      </ul>
      <p className="note">
        另外，<strong>Nasdaq 沒有盤中判讀</strong>。台股的盤中估計靠線性外推，那在台股勉強成立；
        美股的量能是明顯的 U 型，收盤競價常常一根就吃掉全日一成以上，線性外推會系統性低估，
        寧可沒有也不要推一個偏冷的假訊號。
      </p>

      <h2>資料來源與更新</h2>
      <ul>
        <li>
          <strong>台股</strong>：證交所<strong>「市場成交資訊」（FMTQIK）</strong>每日收盤統計，
          取發行量加權股價指數收盤與成交金額（億元），回補至 2016 年。平日 16:00（收盤後）自動同步。
        </li>
        <li>
          <strong>Nasdaq</strong>：Yahoo Finance 的 <span className="mono">^IXIC</span> 日線，取
          Nasdaq Composite 收盤與 composite volume（億股），同樣回補至 2016 年。台北時間每日 06:00
          自動同步——那時美股前一個交易日已經收盤（16:00 ET，夏令 / 冬令都涵蓋得到）。
        </li>
        <li>
          位階常態、量能比、殘差、百分位、判讀<strong>都在讀取時即時計算</strong>，不預先存檔——
          迴歸永遠反映到當下為止的完整歷史。
        </li>
      </ul>

      <h2 id="diff">與原始試算表的數字差異</h2>
      <p>
        原始 Google 試算表的位階常態，用的是<strong>一組固定寫死的係數</strong>
        （<span className="mono">a = −7.750181</span>、<span className="mono">b = 1.608</span>）——
        那是製表當時跑一次迴歸的結果，之後新增資料不會再更新它。
      </p>
      <p>
        本站則是<strong>每次讀取都用當下的完整歷史重新迴歸</strong>。兩者的資料集不同，係數自然
        不同，位階常態因此會有數個百分點的落差，並一路傳導到量能比與殘差。判讀在絕大多數日子仍
        相同，但落在分級邊界附近的日子可能差一級。
      </p>
      <p className="note">
        簡單說：試算表是<strong>凍結的快照</strong>，本站是<strong>會隨資料自我校正的模型</strong>。
      </p>
    </main>
  );
}
