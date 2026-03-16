import { useState, useEffect, useRef, useCallback } from "react";

const DATA = {
  signals:[
    {name:"Pipeline velocity",source:"CRM",dir:"softening",z:"-1.82",alert:true},
    {name:"Pipeline decay",source:"CRM",dir:"deteriorating",z:"+2.14",alert:true},
    {name:"Win rate",source:"CRM",dir:"softening",z:"-1.44",alert:false},
    {name:"Stage stall",source:"CRM",dir:"softening",z:"+1.67",alert:false},
    {name:"Backlog burn",source:"ERP",dir:"softening",z:"-1.92",alert:true},
    {name:"Capacity utilization",source:"ERP",dir:"stable",z:"-0.62",alert:false},
    {name:"Labor efficiency",source:"ERP",dir:"softening",z:"-1.21",alert:false},
    {name:"Inventory coverage",source:"ERP",dir:"softening",z:"+1.34",alert:false},
    {name:"Budget drift",source:"ERP",dir:"softening",z:"+1.78",alert:false},
    {name:"Composite macro",source:"External",dir:"softening",z:"-1.55",alert:false},
    {name:"Commodity pressure",source:"External",dir:"deteriorating",z:"+2.44",alert:true},
    {name:"Unplanned downtime",source:"CMMS",dir:"softening",z:"+1.41",alert:false},
    {name:"PM compliance",source:"CMMS",dir:"softening",z:"-1.68",alert:true},
    {name:"Labor productivity",source:"ERP",dir:"softening",z:"-1.31",alert:false},
    {name:"Yield rate",source:"ERP",dir:"softening",z:"-1.74",alert:true},
    {name:"Material cost var.",source:"ERP",dir:"softening",z:"+1.88",alert:false},
    {name:"Scrap rate",source:"ERP",dir:"softening",z:"+1.52",alert:false},
  ],
  observations:[
    {sev:"high",type:"Cross-system",text:"Pipeline decay (38%) and rising unplanned downtime (3.2%) are converging with softening backlog. All three systems signal the same 60-90 day window.",sys:"CRM + CMMS + ERP"},
    {sev:"high",type:"Maintenance risk",text:"PM compliance at 78% — down 9 points — while capacity utilization remains elevated. Historical pattern shows unplanned downtime accelerates 4-6 weeks after PM compliance drops below 80%.",sys:"CMMS + ERP"},
    {sev:"medium",type:"Yield anomaly",text:"Charlotte facility yield rate dropped to 87.4% — 2.6 std devs below baseline. No work order explains the full gap. Field investigation warranted.",sys:"ERP + File upload"},
  ],
  predictions:[
    {type:"Demand inflection",dir:"softening",conf:"High",horizon:"90d",text:"Pipeline velocity 34.2 avg days in stage — 1.8 std devs above baseline. Win rate declined to 31% from 44%. Demand inflection underway with high confidence."},
    {type:"Margin pressure",dir:"deteriorating",conf:"High",horizon:"60d",text:"Aluminum spot prices 2.4 std devs above baseline. Material cost variance +6.8% over standard. Gross margin compression of 180-220 bps projected in 60-day window."},
  ],
  pipeline:[
    {stage:"Qualified",count:47,value:"$3.2M",pct:38},
    {stage:"Proposal sent",count:31,value:"$2.8M",pct:33},
    {stage:"Negotiation",count:18,value:"$1.6M",pct:19},
    {stage:"Verbal commit",count:9,value:"$0.8M",pct:10},
  ],
  budget:[
    {label:"Revenue",actual:"$4.18M",plan:"$4.40M",varStr:"-5.0%",pct:95,over:false},
    {label:"Labor cost",actual:"$1.12M",plan:"$1.04M",varStr:"+7.7%",pct:108,over:true},
    {label:"Material cost",actual:"$1.38M",plan:"$1.29M",varStr:"+7.0%",pct:107,over:true},
    {label:"Maintenance",actual:"$0.28M",plan:"$0.24M",varStr:"+16.7%",pct:117,over:true},
    {label:"Gross margin",actual:"34.8%",plan:"37.5%",varStr:"-2.7pt",pct:93,over:false},
  ],
  labor:{weeks:["W1","W2","W3","W4","W5","W6","W7","W8"],vals:[12.6,12.4,12.1,12.3,11.9,11.7,11.8,11.8],baseline:12.5},
  yieldData:{weeks:["W1","W2","W3","W4","W5","W6","W7","W8"],yield:[94.1,93.8,93.2,92.4,92.1,91.4,91.2,91.2],scrap:[2.8,3.0,3.4,3.8,4.0,4.4,4.6,4.6]},
};

const FACILITIES = {
  all:  {lp:"11.8",lpDelta:"↓ 0.7 vs baseline",yr:"91.2%",yrDelta:"↓ 2.8% vs baseline"},
  atl:  {lp:"11.8",lpDelta:"↓ 0.7 vs baseline",yr:"91.2%",yrDelta:"↓ 2.8% vs baseline"},
  clt:  {lp:"10.4",lpDelta:"↓ 2.1 vs baseline",yr:"87.4%",yrDelta:"↓ 6.7% vs baseline"},
  mem:  {lp:"13.1",lpDelta:"↑ 0.6 vs baseline",yr:"94.8%",yrDelta:"↑ 0.7% vs baseline"},
};

const dirColor = d => ({improving:"#22c55e",stable:"#94a3b8",softening:"#f59e0b",deteriorating:"#ef4444"}[d]||"#94a3b8");
const dirLabel = d => ({improving:"↑ Improving",stable:"→ Stable",softening:"↓ Softening",deteriorating:"↓↓ Deteriorating"}[d]||d);
const sevColor = s => ({high:"#ef4444",medium:"#f59e0b",low:"#94a3b8"}[s]||"#94a3b8");
const sevBg    = s => ({high:"#fef2f2",medium:"#fffbeb",low:"#f8fafc"}[s]||"#f8fafc");

const CONTEXT = `You are the Huckle intelligence assistant for Meridian Glass & Aluminum, a glass/aluminum fabricator with 3 facilities (Atlanta, Charlotte, Memphis).
SIGNALS: Pipeline velocity z=-1.82 softening, Pipeline decay z=+2.14 deteriorating, Win rate 31% (baseline 44%), PM compliance 78% (down 9pts) ALERT, Unplanned downtime 3.2%, Labor productivity 11.8 units/hr (baseline 12.5), Yield rate 91.2% (baseline 94.1%) ALERT, Material cost variance +6.8%, Commodity pressure z=+2.44 deteriorating ALERT.
FACILITIES: Atlanta (yield 91.2%, OEE 78%, 2 alerts), Charlotte (yield 87.4%, OEE 71%, 3 alerts), Memphis (yield 94.8%, OEE 84%, healthy).
BUDGET MTD: Revenue -5% vs plan, Labor +7.7% over, Materials +7.0% over, Maintenance +16.7% over, Gross margin 34.8% vs 37.5% plan.
PREDICTIONS: Demand Inflection High/90d softening. Margin Pressure High/60d deteriorating.
OBSERVATIONS: Cross-system convergence CRM+CMMS+ERP all adverse. PM compliance collision course in 4-6 weeks. Charlotte yield anomaly 2.6 std devs below baseline.
Answer directly with specific numbers. 2-3 sentences max. No hedging.`;

export default function App() {
  const [facility, setFacility] = useState("all");
  const [timeView, setTimeView]  = useState("mtd");
  const [chatOpen, setChatOpen]  = useState(false);
  const [messages, setMessages]  = useState([{role:"assistant",content:"I have full visibility into Meridian Glass operations across all three facilities. Ask me anything."}]);
  const [input, setInput]        = useState("");
  const [loading, setLoading]    = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const messagesEnd = useRef(null);

  useEffect(() => { messagesEnd.current?.scrollIntoView({behavior:"smooth"}); }, [messages]);

  const fData = FACILITIES[facility] || FACILITIES.all;

  const sendMessage = useCallback(async (text) => {
    const msg = text || input.trim();
    if (!msg || loading) return;
    setInput("");
    setMessages(m => [...m, {role:"user",content:msg}]);
    setLoading(true);
    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({model:"claude-sonnet-4-20250514",max_tokens:400,system:CONTEXT,messages:[...messages.filter((_,i)=>i>0).map(m=>({role:m.role,content:m.content})),{role:"user",content:msg}]}),
      });
      const data = await res.json();
      setMessages(m => [...m, {role:"assistant",content:data.content?.[0]?.text||"Error processing request."}]);
    } catch(e) {
      setMessages(m => [...m, {role:"assistant",content:"Connection error. Please try again."}]);
    }
    setLoading(false);
  }, [input, loading, messages]);

  const ss = { minHeight:"100vh", background:"#0a0f1e", color:"#e2e8f0", fontFamily:"-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif", fontSize:14 };

  const topBar = {
    background:"#0f172a", borderBottom:"1px solid #1e293b", padding:"0 20px",
    display:"flex", alignItems:"center", gap:16, height:52, flexShrink:0, flexWrap:"wrap",
  };

  const Card = ({children, style={}}) => (
    <div style={{background:"#0f172a",border:"1px solid #1e293b",borderRadius:10,padding:"14px 16px",...style}}>
      {children}
    </div>
  );

  const Metric = ({label, value, delta, deltaDown=true, sub=""}) => (
    <div style={{background:"#0d1a2d",borderRadius:8,padding:"12px 14px"}}>
      <div style={{fontSize:11,color:"#64748b",marginBottom:4,letterSpacing:"0.05em"}}>{label}</div>
      <div style={{fontSize:20,fontWeight:600,color:"#f1f5f9"}}>{value}</div>
      {delta && <div style={{fontSize:11,marginTop:3,color:deltaDown?"#f59e0b":"#22c55e"}}>{delta}</div>}
      {sub && <div style={{fontSize:10,color:"#475569",marginTop:2}}>{sub}</div>}
    </div>
  );

  const Badge = ({children, color="#f59e0b", bg}) => (
    <span style={{display:"inline-flex",alignItems:"center",padding:"2px 8px",borderRadius:5,fontSize:11,fontWeight:600,color,background:bg||(color+"18"),border:`1px solid ${color}30`}}>{children}</span>
  );

  const FacBtn = ({id, label, status, detail}) => (
    <div onClick={()=>setFacility(id)} style={{background:facility===id?"#0f2a4a":"#0d1526",border:`1px solid ${facility===id?"#3b82f6":"#1e293b"}`,borderRadius:8,padding:"10px 14px",cursor:"pointer",flex:1}}>
      <div style={{fontSize:13,fontWeight:600,color:"#f1f5f9",marginBottom:4}}>{label}</div>
      <Badge color={status==="Healthy"?"#22c55e":status==="3 alerts"?"#ef4444":"#f59e0b"}>{status}</Badge>
      <div style={{fontSize:11,color:"#64748b",marginTop:6}}>{detail}</div>
    </div>
  );

  const TabBtn = ({id, label}) => (
    <button onClick={()=>setActiveTab(id)} style={{padding:"6px 16px",borderRadius:6,border:activeTab===id?"1px solid #3b82f6":"1px solid #1e293b",background:activeTab===id?"#1d4ed820":"transparent",color:activeTab===id?"#60a5fa":"#64748b",fontSize:13,cursor:"pointer"}}>
      {label}
    </button>
  );

  return (
    <div style={ss}>
      {/* TOP BAR */}
      <div style={topBar}>
        <div style={{fontWeight:700,fontSize:15,color:"#f1f5f9"}}>
          <span style={{color:"#3b82f6"}}>H</span>uckleberry
        </div>
        <div style={{width:1,height:24,background:"#1e293b"}} />
        <div style={{fontSize:12,color:"#64748b"}}>Meridian Glass & Aluminum</div>
        <div style={{marginLeft:"auto",display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
          {/* Facility tabs */}
          {["all","atl","clt","mem"].map((f,i) => (
            <button key={f} onClick={()=>setFacility(f)} style={{padding:"4px 12px",borderRadius:6,border:facility===f?"1px solid #3b82f6":"1px solid #1e293b",background:facility===f?"#1d4ed820":"transparent",color:facility===f?"#60a5fa":"#64748b",fontSize:12,cursor:"pointer"}}>
              {["All Facilities","Atlanta","Charlotte","Memphis"][i]}
            </button>
          ))}
          <div style={{width:1,height:20,background:"#1e293b"}} />
          {/* Time toggle */}
          <div style={{display:"flex",gap:2,background:"#0d1526",borderRadius:6,padding:3,border:"1px solid #1e293b"}}>
            {["mtd","30d","wow"].map(t => (
              <button key={t} onClick={()=>setTimeView(t)} style={{padding:"3px 10px",borderRadius:4,border:timeView===t?"1px solid #334155":"none",background:timeView===t?"#1e293b":"transparent",color:timeView===t?"#e2e8f0":"#64748b",fontSize:12,cursor:"pointer",textTransform:"uppercase"}}>
                {t}
              </button>
            ))}
          </div>
          <button onClick={()=>setChatOpen(o=>!o)} style={{background:chatOpen?"#1d4ed8":"#1e293b",border:`1px solid ${chatOpen?"#3b82f6":"#334155"}`,borderRadius:8,padding:"5px 14px",color:"#e2e8f0",fontSize:12,fontWeight:600,cursor:"pointer"}}>
            ✦ Intelligence Chat
          </button>
        </div>
      </div>

      {/* STATUS BAR */}
      <div style={{background:"#0d1526",borderBottom:"1px solid #1e293b",padding:"8px 20px",display:"flex",gap:28,flexWrap:"wrap"}}>
        {[
          {l:"ADVERSE SIGNALS",v:"9/17",c:"#f59e0b"},
          {l:"ACTIVE ALERTS",v:"5",c:"#ef4444"},
          {l:"ACTIVE PREDICTIONS",v:"2",c:"#f59e0b"},
          {l:"DEMAND CONFIDENCE",v:"High · 0.812",c:"#22c55e"},
          {l:"GROSS MARGIN MTD",v:"34.8% (plan 37.5%)",c:"#ef4444"},
          {l:"LAST SIGNAL COMPUTE",v:"Mar 15 · 07:00 UTC",c:"#64748b"},
        ].map(s => (
          <div key={s.l}>
            <div style={{fontSize:10,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:1}}>{s.l}</div>
            <div style={{fontSize:12,color:s.c,fontWeight:700,fontFamily:"monospace"}}>{s.v}</div>
          </div>
        ))}
      </div>

      {/* MAIN + CHAT */}
      <div style={{display:"flex",flex:1,overflow:"hidden"}}>
        <div style={{flex:1,overflow:"auto",padding:"20px"}}>

          {/* Section nav */}
          <div style={{display:"flex",gap:6,marginBottom:20,flexWrap:"wrap"}}>
            <TabBtn id="overview" label="Overview" />
            <TabBtn id="labor" label="Labor & Productivity" />
            <TabBtn id="materials" label="Materials & Yield" />
            <TabBtn id="maintenance" label="Maintenance" />
            <TabBtn id="sales" label="Sales Pipeline" />
            <TabBtn id="budget" label="Budget vs Actual" />
            <TabBtn id="signals" label="Signal Health" />
            <TabBtn id="intelligence" label="Intelligence" />
          </div>

          {/* OVERVIEW */}
          {activeTab === "overview" && (
            <div style={{display:"flex",flexDirection:"column",gap:16}}>
              <div style={{display:"flex",gap:10}}>
                <FacBtn id="all" label="All Facilities" status="5 alerts" detail="Rollup · 3 facilities" />
                <FacBtn id="atl" label="Atlanta" status="2 alerts" detail="Yield 91.2% · OEE 78%" />
                <FacBtn id="clt" label="Charlotte" status="3 alerts" detail="Yield 87.4% · OEE 71%" />
                <FacBtn id="mem" label="Memphis" status="Healthy" detail="Yield 94.8% · OEE 84%" />
              </div>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
                <Metric label="Labor productivity" value={fData.lp} delta={fData.lpDelta} sub="units/hr" />
                <Metric label="Yield rate" value={fData.yr} delta={fData.yrDelta} sub="good / started" />
                <Metric label="PM compliance" value="78%" delta="↓ 9% vs baseline" sub="on-schedule" />
                <Metric label="Win rate" value="31%" delta="↓ 13% vs baseline" sub="closed won" />
              </div>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
                <Metric label="Unplanned downtime" value="3.2%" delta="↑ 1.4% vs baseline" sub="of avail. hours" />
                <Metric label="Scrap rate" value="4.6%" delta="↑ 1.9% vs baseline" sub="units scrapped" />
                <Metric label="Material cost var." value="+6.8%" delta="Over standard" sub="actual vs std" />
                <Metric label="Gross margin MTD" value="34.8%" delta="↓ 2.7pt vs plan" deltaDown={true} sub="plan: 37.5%" />
              </div>
              {/* Active predictions */}
              <Card>
                <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:12}}>ACTIVE PREDICTIONS</div>
                {DATA.predictions.map((p,i) => (
                  <div key={i} style={{borderLeft:`3px solid ${dirColor(p.dir)}`,paddingLeft:12,marginBottom:i<DATA.predictions.length-1?16:0}}>
                    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
                      <span style={{fontSize:14,fontWeight:600,color:"#f1f5f9"}}>{p.type}</span>
                      <Badge color={dirColor(p.dir)}>{dirLabel(p.dir)}</Badge>
                      <Badge color="#22c55e">{p.conf} · {p.horizon}</Badge>
                    </div>
                    <div style={{fontSize:12,color:"#94a3b8",lineHeight:1.6}}>{p.text}</div>
                  </div>
                ))}
              </Card>
            </div>
          )}

          {/* LABOR */}
          {activeTab === "labor" && (
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
                <Metric label="Labor productivity" value={fData.lp} delta={fData.lpDelta} sub="units/hr" />
                <Metric label="Labor hours worked" value="14,820" delta="→ on plan" deltaDown={false} sub="this period" />
                <Metric label="Overtime rate" value="8.4%" delta="↑ 2.1% vs prior" sub="of total hours" />
                <Metric label="Cost per unit" value="$4.82" delta="↑ $0.31 vs baseline" sub="fully loaded" />
              </div>
              <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:10}}>
                <Metric label="Headcount total" value="247" delta="→ no change" deltaDown={false} sub="all facilities" />
                <Metric label="Absenteeism rate" value="3.8%" delta="↑ 0.9% vs avg" sub="rolling 30d" />
                <Metric label="Training hours" value="142" delta="↓ 31 vs plan" sub="MTD" />
              </div>
              <Card>
                <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:10}}>PRODUCTIVITY BY FACILITY — CURRENT VS BASELINE</div>
                {[
                  {fac:"Atlanta",cur:11.8,base:12.5,pct:94},
                  {fac:"Charlotte",cur:10.4,base:12.5,pct:83},
                  {fac:"Memphis",cur:13.1,base:12.5,pct:105},
                ].map(f => (
                  <div key={f.fac} style={{marginBottom:12}}>
                    <div style={{display:"flex",justifyContent:"space-between",fontSize:13,marginBottom:4}}>
                      <span style={{color:"#e2e8f0"}}>{f.fac}</span>
                      <span style={{fontFamily:"monospace",color:f.cur<f.base?"#f59e0b":"#22c55e"}}>{f.cur} units/hr (baseline {f.base})</span>
                    </div>
                    <div style={{background:"#1e293b",borderRadius:4,height:8}}>
                      <div style={{height:"100%",borderRadius:4,background:f.cur<f.base?"#f59e0b":"#22c55e",width:`${Math.min(f.pct,110)}%`,transition:"width 0.3s"}} />
                    </div>
                  </div>
                ))}
              </Card>
            </div>
          )}

          {/* MATERIALS */}
          {activeTab === "materials" && (
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
                <Metric label="Yield rate" value={fData.yr} delta={fData.yrDelta} sub="good / started" />
                <Metric label="Scrap rate" value="4.6%" delta="↑ 1.9% vs baseline" sub="units scrapped" />
                <Metric label="Material cost var." value="+6.8%" delta="Over standard" sub="actual vs std" />
                <Metric label="Scrap cost MTD" value="$94K" delta="↑ $28K vs plan" sub="material waste" />
              </div>
              <Card>
                <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:10}}>YIELD BY FACILITY</div>
                {[
                  {fac:"Atlanta",yield:91.2,base:94.1,scrap:4.6},
                  {fac:"Charlotte",yield:87.4,base:94.1,scrap:7.2},
                  {fac:"Memphis",yield:94.8,base:94.1,scrap:2.8},
                ].map(f => (
                  <div key={f.fac} style={{display:"grid",gridTemplateColumns:"120px 1fr 100px 80px",gap:12,alignItems:"center",padding:"8px 0",borderBottom:"1px solid #1e293b"}}>
                    <span style={{fontSize:13,color:"#e2e8f0"}}>{f.fac}</span>
                    <div style={{background:"#1e293b",borderRadius:4,height:8}}>
                      <div style={{height:"100%",borderRadius:4,background:f.yield<f.base?"#f59e0b":"#22c55e",width:`${f.yield}%`}} />
                    </div>
                    <span style={{fontFamily:"monospace",fontSize:12,color:f.yield<f.base?"#f59e0b":"#22c55e",textAlign:"right"}}>{f.yield}%</span>
                    <span style={{fontSize:11,color:"#64748b",textAlign:"right"}}>scrap {f.scrap}%</span>
                  </div>
                ))}
              </Card>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
                <Card>
                  <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:10}}>MATERIAL COST VARIANCE BY CATEGORY</div>
                  {[
                    {cat:"Float glass",var:"+4.2%",over:true},
                    {cat:"Aluminum extrusion",var:"+11.8%",over:true},
                    {cat:"Sealants / spacers",var:"+2.1%",over:true},
                    {cat:"Packaging",var:"-1.4%",over:false},
                  ].map(m => (
                    <div key={m.cat} style={{display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:"1px solid #1e293b",fontSize:13}}>
                      <span style={{color:"#94a3b8"}}>{m.cat}</span>
                      <span style={{fontFamily:"monospace",color:m.over?"#f59e0b":"#22c55e",fontWeight:600}}>{m.var}</span>
                    </div>
                  ))}
                </Card>
                <Card>
                  <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:10}}>SCRAP BY CAUSE — MTD</div>
                  {[
                    {cause:"Tempering breakage",units:142,pct:38},
                    {cause:"Edge defect",units:98,pct:26},
                    {cause:"Coating failure",units:74,pct:20},
                    {cause:"Handling damage",units:60,pct:16},
                  ].map(s => (
                    <div key={s.cause} style={{marginBottom:8}}>
                      <div style={{display:"flex",justifyContent:"space-between",fontSize:12,marginBottom:3}}>
                        <span style={{color:"#94a3b8"}}>{s.cause}</span>
                        <span style={{color:"#e2e8f0",fontFamily:"monospace"}}>{s.units} units · {s.pct}%</span>
                      </div>
                      <div style={{background:"#1e293b",borderRadius:3,height:5}}>
                        <div style={{height:"100%",borderRadius:3,background:"#ef4444",width:`${s.pct}%`}} />
                      </div>
                    </div>
                  ))}
                </Card>
              </div>
            </div>
          )}

          {/* MAINTENANCE */}
          {activeTab === "maintenance" && (
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
                <Metric label="PM compliance" value="78%" delta="↓ 9% vs baseline" sub="on-schedule" />
                <Metric label="Unplanned downtime" value="3.2%" delta="↑ 1.4% vs baseline" sub="of avail. hours" />
                <Metric label="MTTR" value="4.8 hrs" delta="↑ 1.2 vs baseline" sub="mean time to repair" />
                <Metric label="Open work orders" value="34" delta="↑ 12 vs 30d avg" sub="backlog" />
              </div>
              <Card>
                <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:10}}>PM COMPLIANCE BY FACILITY</div>
                {[
                  {fac:"Atlanta",rate:82,target:90},
                  {fac:"Charlotte",rate:71,target:90},
                  {fac:"Memphis",rate:88,target:90},
                ].map(f => (
                  <div key={f.fac} style={{marginBottom:12}}>
                    <div style={{display:"flex",justifyContent:"space-between",fontSize:13,marginBottom:4}}>
                      <span style={{color:"#e2e8f0"}}>{f.fac}</span>
                      <span style={{fontFamily:"monospace",color:f.rate<f.target?"#f59e0b":"#22c55e"}}>{f.rate}% (target {f.target}%)</span>
                    </div>
                    <div style={{background:"#1e293b",borderRadius:4,height:8,position:"relative"}}>
                      <div style={{height:"100%",borderRadius:4,background:f.rate<f.target?"#f59e0b":"#22c55e",width:`${f.rate}%`}} />
                      <div style={{position:"absolute",top:0,left:`${f.target}%`,width:2,height:"100%",background:"#475569"}} />
                    </div>
                  </div>
                ))}
              </Card>
              <Card>
                <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:10}}>TOP OPEN WORK ORDERS BY PRIORITY</div>
                {[
                  {asset:"Tempering furnace #2",fac:"Charlotte",type:"Unplanned",priority:"Critical",age:"8d"},
                  {asset:"Conveyor line B",fac:"Atlanta",type:"Unplanned",priority:"High",age:"5d"},
                  {asset:"Autoclave #1",fac:"Atlanta",type:"PM overdue",priority:"High",age:"12d"},
                  {asset:"Edge grinder #3",fac:"Charlotte",type:"Unplanned",priority:"Medium",age:"3d"},
                  {asset:"Air compressor",fac:"Memphis",type:"PM overdue",priority:"Medium",age:"7d"},
                ].map((w,i) => (
                  <div key={i} style={{display:"grid",gridTemplateColumns:"2fr 1fr 1fr 80px 50px",gap:8,alignItems:"center",padding:"8px 0",borderBottom:"1px solid #1e293b",fontSize:12}}>
                    <span style={{color:"#e2e8f0"}}>{w.asset}</span>
                    <span style={{color:"#64748b"}}>{w.fac}</span>
                    <span style={{color:"#94a3b8"}}>{w.type}</span>
                    <Badge color={w.priority==="Critical"?"#ef4444":w.priority==="High"?"#f59e0b":"#94a3b8"}>{w.priority}</Badge>
                    <span style={{color:"#64748b",textAlign:"right"}}>{w.age}</span>
                  </div>
                ))}
              </Card>
            </div>
          )}

          {/* SALES */}
          {activeTab === "sales" && (
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
                <Metric label="Win rate" value="31%" delta="↓ 13% vs baseline" sub="closed won" />
                <Metric label="Pipeline value" value="$8.4M" delta="→ flat vs prior" deltaDown={false} sub="total open" />
                <Metric label="Avg days to close" value="34d" delta="↑ 12d vs baseline" sub="pipeline velocity" />
                <Metric label="Decay rate" value="38%" delta="↑ 19% vs baseline" sub="no activity 30d" />
              </div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
                <Card>
                  <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:12}}>PIPELINE BY STAGE</div>
                  {DATA.pipeline.map(p => (
                    <div key={p.stage} style={{marginBottom:10}}>
                      <div style={{display:"flex",justifyContent:"space-between",fontSize:13,marginBottom:3}}>
                        <span style={{color:"#e2e8f0"}}>{p.stage}</span>
                        <span style={{color:"#64748b"}}>{p.count} deals · {p.value}</span>
                      </div>
                      <div style={{background:"#1e293b",borderRadius:4,height:8}}>
                        <div style={{height:"100%",borderRadius:4,background:"#3b82f6",width:`${p.pct}%`}} />
                      </div>
                    </div>
                  ))}
                </Card>
                <Card>
                  <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:12}}>WIN RATE BY REGION — ROLLING 30D</div>
                  {[
                    {region:"Southeast",rate:28,base:44,deals:31},
                    {region:"Mid-Atlantic",rate:38,base:44,deals:24},
                    {region:"Midwest",rate:34,base:44,deals:18},
                    {region:"Northeast",rate:41,base:44,deals:14},
                  ].map(r => (
                    <div key={r.region} style={{display:"grid",gridTemplateColumns:"100px 1fr 60px",gap:10,alignItems:"center",padding:"7px 0",borderBottom:"1px solid #1e293b",fontSize:12}}>
                      <span style={{color:"#94a3b8"}}>{r.region}</span>
                      <div style={{background:"#1e293b",borderRadius:4,height:6}}>
                        <div style={{height:"100%",borderRadius:4,background:r.rate<r.base?"#f59e0b":"#22c55e",width:`${r.rate}%`}} />
                      </div>
                      <span style={{fontFamily:"monospace",color:r.rate<r.base?"#f59e0b":"#22c55e",textAlign:"right"}}>{r.rate}%</span>
                    </div>
                  ))}
                </Card>
              </div>
            </div>
          )}

          {/* BUDGET */}
          {activeTab === "budget" && (
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <Card>
                <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:12}}>BUDGET VS ACTUAL — MTD</div>
                {DATA.budget.map(b => (
                  <div key={b.label} style={{display:"grid",gridTemplateColumns:"140px 1fr 90px 70px 70px",gap:12,alignItems:"center",padding:"9px 0",borderBottom:"1px solid #1e293b",fontSize:13}}>
                    <span style={{color:"#94a3b8"}}>{b.label}</span>
                    <div style={{background:"#1e293b",borderRadius:4,height:6}}>
                      <div style={{height:"100%",borderRadius:4,background:b.over?"#ef4444":"#22c55e",width:`${Math.min(b.pct,130)/1.3}%`}} />
                    </div>
                    <span style={{color:"#e2e8f0",fontFamily:"monospace",textAlign:"right"}}>{b.actual}</span>
                    <span style={{color:"#64748b",fontSize:11,textAlign:"right"}}>plan {b.plan}</span>
                    <span style={{fontFamily:"monospace",color:b.over?"#f59e0b":"#22c55e",textAlign:"right",fontWeight:600}}>{b.varStr}</span>
                  </div>
                ))}
              </Card>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
                <Metric label="Revenue vs plan" value="-5.0%" delta="$220K below" sub="MTD" />
                <Metric label="Labor over plan" value="+$80K" delta="+7.7% variance" sub="MTD" />
                <Metric label="Materials over plan" value="+$90K" delta="+7.0% variance" sub="MTD" />
                <Metric label="Margin compression" value="-2.7pt" delta="34.8% actual" sub="plan was 37.5%" />
              </div>
            </div>
          )}

          {/* SIGNALS */}
          {activeTab === "signals" && (
            <Card>
              <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:12}}>ALL 17 SIGNALS — LAST COMPUTATION MAR 15 · 07:00 UTC</div>
              {DATA.signals.map((s,i) => (
                <div key={i} style={{display:"grid",gridTemplateColumns:"1fr 120px 50px 80px",gap:8,alignItems:"center",padding:"8px 0",borderBottom:"1px solid #1e293b"}}>
                  <div>
                    <div style={{fontSize:13,color:"#e2e8f0",display:"flex",alignItems:"center",gap:6}}>
                      {s.name}
                      {s.alert && <span style={{width:6,height:6,borderRadius:"50%",background:"#ef4444",display:"inline-block"}} />}
                    </div>
                    <div style={{fontSize:11,color:"#475569"}}>{s.source}</div>
                  </div>
                  <Badge color={dirColor(s.dir)}>{dirLabel(s.dir)}</Badge>
                  <span style={{fontFamily:"monospace",fontSize:11,color:"#64748b",textAlign:"right"}}>z={s.z}</span>
                  <Badge color="#64748b">High</Badge>
                </div>
              ))}
            </Card>
          )}

          {/* INTELLIGENCE */}
          {activeTab === "intelligence" && (
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <Card>
                <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:12}}>INTELLIGENCE OBSERVATIONS — MAR 15 NIGHTLY SCAN</div>
                {DATA.observations.map((o,i) => (
                  <div key={i} style={{padding:"12px 0",borderBottom:i<DATA.observations.length-1?"1px solid #1e293b":"none"}}>
                    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}>
                      <Badge color={sevColor(o.sev)} bg={sevBg(o.sev)}>{o.sev.charAt(0).toUpperCase()+o.sev.slice(1)}</Badge>
                      <span style={{fontSize:12,color:"#64748b"}}>{o.type} · {o.sys}</span>
                    </div>
                    <div style={{fontSize:13,color:"#94a3b8",lineHeight:1.7}}>{o.text}</div>
                  </div>
                ))}
              </Card>
              <Card>
                <div style={{fontSize:11,color:"#475569",letterSpacing:"0.08em",fontWeight:600,marginBottom:12}}>ACTIVE PREDICTIONS WITH SCENARIOS</div>
                {DATA.predictions.map((p,i) => (
                  <div key={i} style={{borderLeft:`3px solid ${dirColor(p.dir)}`,paddingLeft:14,marginBottom:i<DATA.predictions.length-1?20:0}}>
                    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}>
                      <span style={{fontSize:14,fontWeight:600,color:"#f1f5f9"}}>{p.type}</span>
                      <Badge color={dirColor(p.dir)}>{dirLabel(p.dir)}</Badge>
                      <Badge color="#22c55e">{p.conf} confidence · {p.horizon}</Badge>
                    </div>
                    <div style={{fontSize:13,color:"#94a3b8",lineHeight:1.6,marginBottom:10}}>{p.text}</div>
                    <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8}}>
                      {["Conservative","Balanced","Aggressive"].map((sc,j) => (
                        <div key={sc} style={{background:"#0d1a2d",borderRadius:8,padding:"10px 12px",border:`1px solid ${["#ef4444","#f59e0b","#22c55e"][j]}20`}}>
                          <div style={{fontSize:12,fontWeight:600,color:["#ef4444","#f59e0b","#22c55e"][j],marginBottom:6}}>{sc}</div>
                          <div style={{fontSize:11,color:"#64748b"}}>Net outcome 90d</div>
                          <div style={{fontSize:14,fontFamily:"monospace",color:"#e2e8f0",marginTop:2}}>{["-$324K","-$336K","-$270K"][j]}</div>
                          <div style={{fontSize:11,color:"#64748b",marginTop:4}}>HC change: {["-18","-7","0"][j]}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </Card>
            </div>
          )}

        </div>

        {/* CHAT PANEL */}
        {chatOpen && (
          <div style={{width:360,background:"#0d1526",borderLeft:"1px solid #1e293b",display:"flex",flexDirection:"column",flexShrink:0}}>
            <div style={{padding:"12px 16px",borderBottom:"1px solid #1e293b",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
              <div>
                <div style={{fontSize:14,fontWeight:600,color:"#f1f5f9"}}>✦ Intelligence Chat</div>
                <div style={{fontSize:11,color:"#475569"}}>Grounded in Meridian Glass data</div>
              </div>
              <button onClick={()=>setChatOpen(false)} style={{background:"none",border:"none",color:"#475569",cursor:"pointer",fontSize:20,lineHeight:1}}>×</button>
            </div>
            <div style={{flex:1,overflowY:"auto",padding:14,display:"flex",flexDirection:"column",gap:10}}>
              {messages.map((m,i) => (
                <div key={i} style={{display:"flex",justifyContent:m.role==="user"?"flex-end":"flex-start"}}>
                  <div style={{maxWidth:"88%",background:m.role==="user"?"#1d4ed8":"#1e293b",borderRadius:m.role==="user"?"12px 12px 2px 12px":"12px 12px 12px 2px",padding:"9px 13px",fontSize:13,color:"#e2e8f0",lineHeight:1.6}}>
                    {m.content}
                  </div>
                </div>
              ))}
              {loading && (
                <div style={{display:"flex"}}>
                  <div style={{background:"#1e293b",borderRadius:"12px 12px 12px 2px",padding:"10px 14px",display:"flex",gap:4}}>
                    {[0,1,2].map(i => <div key={i} style={{width:6,height:6,borderRadius:"50%",background:"#3b82f6",opacity:0.6}} />)}
                  </div>
                </div>
              )}
              <div ref={messagesEnd} />
            </div>
            <div style={{padding:"8px 12px",borderTop:"1px solid #1e293b",display:"flex",flexWrap:"wrap",gap:4}}>
              {["Why is Charlotte yield low?","PM compliance drop?","Demand prediction?"].map(q => (
                <button key={q} onClick={()=>sendMessage(q)} style={{background:"#1e293b",border:"1px solid #334155",borderRadius:5,padding:"3px 8px",color:"#94a3b8",fontSize:11,cursor:"pointer"}}>{q}</button>
              ))}
            </div>
            <div style={{padding:"10px 12px",borderTop:"1px solid #1e293b",display:"flex",gap:8}}>
              <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&sendMessage()} placeholder="Ask about operations..." style={{flex:1,background:"#1e293b",border:"1px solid #334155",borderRadius:8,padding:"8px 12px",color:"#e2e8f0",fontSize:13,outline:"none"}} />
              <button onClick={()=>sendMessage()} disabled={loading||!input.trim()} style={{background:"#1d4ed8",border:"none",borderRadius:8,padding:"8px 14px",color:"white",fontSize:13,fontWeight:600,cursor:"pointer",opacity:loading||!input.trim()?0.5:1}}>→</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
