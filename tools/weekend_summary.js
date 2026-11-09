// Prints a short weekend summary from the GitHub page itself (Today tab), for the Monday phone notification.
// usage: (from the repo folder) python3 -m http.server 8765 & node tools/weekend_summary.js
const {chromium}=require("playwright");
(async()=>{
  const b=await chromium.launch();const p=await b.newPage({locale:"en-GB",timezoneId:"Europe/London"});
  await p.route("**/markbrown3000.github.io/**",r=>{const u=new URL(r.request().url());r.fulfill({path:process.cwd()+"/"+u.pathname.replace("/pitch-oracle/","")})});
  await p.route(/^https?:\/\/(?!localhost|markbrown)/,r=>r.abort());
  await p.goto("http://localhost:8765/index.html");await p.waitForTimeout(15000);
  await p.click("#sport button[data-s=today]");await p.waitForTimeout(1500);
  const head=await p.textContent("#tdRecapH");
  const tiles=await p.$$eval("#tdRecap .stat",a=>a.map(x=>{const t=x.innerText.split("\n").map(s=>s.trim()).filter(Boolean);return `${t[0][0]+t[0].slice(1).toLowerCase()}: ${t.slice(1).join(", ")}`}));
  const picks=[];
  for(const d of ["0","1"]){await p.click(`#tdDay button[data-v="${d}"]`);await p.waitForTimeout(500);
    picks.push(...await p.$$eval("#tdList .at-row",(a,d)=>a.slice(0,4).map(x=>`${d==="0"?"Today":"Tomorrow"} ${x.querySelector(".run")?.innerText.replace(/\n/g," ")} · ${x.querySelector(".who")?.innerText} ${x.querySelector(".pl")?.innerText}`),d))}
  console.log(head);tiles.filter(t=>!t.startsWith("Your bets")).forEach(t=>console.log("- "+t));   // logged bets live on the phone, not here
  console.log(picks.length?"Top picks:":"No strong picks for today or tomorrow yet.");picks.forEach(t=>console.log("- "+t));
  await b.close();
})();
