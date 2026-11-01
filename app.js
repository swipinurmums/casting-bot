const DEMO_OPPORTUNITIES = [
  {id:"demo-1",title:"E-commerce fashion campaign",category:"Fashion",compensation:"Paid",location:"London",deadline:"2026-11-18",source:"Example brand casting",url:"https://example.com",description:"Illustrative listing showing how a paid commercial fashion brief will appear. This is not a real casting.",added:"2026-11-01",status:"New",saved:false,demo:true},
  {id:"demo-2",title:"Independent designer editorial shoot",category:"Editorial",compensation:"TFP",location:"Manchester",deadline:"2026-11-12",source:"Example photographer call",url:"https://example.com",description:"Illustrative TFP collaboration with portfolio images and agreed usage terms. Not a real casting.",added:"2026-10-31",status:"New",saved:false,demo:true},
  {id:"demo-3",title:"New faces agency open call",category:"Other",compensation:"Unknown",location:"Remote / UK-wide",deadline:"2026-11-25",source:"Example agency open call",url:"https://example.com",description:"Illustrative open call. Compensation and any representation terms would need checking with the agency.",added:"2026-10-30",status:"New",saved:false,demo:true}
];
const STORAGE_KEY = "radar-opportunities-v1";
const $ = (selector) => document.querySelector(selector);
let opportunities = loadOpportunities();

const PROFILE_KEY = "radar-private-profile-v1";
const PROFILE_FIELDS = ["gender","ageRange","height","base","travel","neck","chest","waist","hips","sleeve","insideLeg","shoe","naturalWaist","otherMeasurements","hair","eyes","appearance","facialHair","otherAppearance","experience","fashion","swimwear","underwear","fitness","beauty","jewellery","commercial"];
function loadProfile(){try{return JSON.parse(localStorage.getItem(PROFILE_KEY)||"{}");}catch{return {};}}
let profile=loadProfile();
function hasProfile(){return PROFILE_FIELDS.some(key=>typeof profile[key]==="boolean"?profile[key]:String(profile[key]||"").trim().length>0);}
async function loadSources(){try{const response=await fetch("data/sources.json?updated="+Date.now(),{cache:"no-store"});if(!response.ok)throw new Error("Unavailable");const data=await response.json();const groups={opportunity_repost:"Casting feeds",model_agency:"Agency accounts",creative_opportunities:"Creative opportunities"};const visible=(data.sources||[]).filter(s=>s.enabled);$("#source-count").textContent=visible.length+" tracked";$("#source-list").innerHTML=visible.map(s=>'<a class="source-chip" href="'+escapeHtml(s.url)+'" target="_blank" rel="noopener noreferrer"><span class="source-dot"></span><span><strong>@'+escapeHtml(s.handle||s.name)+'</strong><small>'+escapeHtml(groups[s.source_group]||"Manual review")+'</small></span><em>↗</em></a>').join("");}catch(error){$("#source-count").textContent="Unavailable";$("#source-list").textContent="Could not load source directory.";}}
function saveProfile(){localStorage.setItem(PROFILE_KEY,JSON.stringify(profile));}
function profileFormOpen(){
 const form=$("#profile-form");
 for(const key of PROFILE_FIELDS){const field=form.elements.namedItem(key);if(!field)continue;if(field.type==="checkbox")field.checked=Boolean(profile[key]);else field.value=profile[key]||"";}
 $("#profile-dialog").showModal();
}
function matchFor(item){
 const text=[item.title,item.description,item.source,item.category].join(" ").toLowerCase(),location=(item.location||"").toLowerCase();
 const flags=[];let score=0,review=false,unsuitable=false;
 if(/\b(nude|nudity|implied nude|artistic nude)\b/.test(text)){unsuitable=true;flags.push("Nudity is outside your stated boundaries");}
 if(/\b(underwear|lingerie)\b/.test(text)){review=true;flags.push("Underwear brief requires individual approval");}
 if(/\b(female only|women only|woman only|girls only)\b/.test(text)&&/male/i.test(profile.gender||"")){unsuitable=true;flags.push("Brief appears to specify a different gender category");}
 const interests=[[/\b(swimwear|swimsuit|beachwear)\b/,"swimwear","Swimwear interest"],[/\b(beauty|skincare|skin care|cosmetic)\b/,"beauty","Beauty/skincare interest"],[/\b(jewellery|jewelry|watch|accessories)\b/,"jewellery","Jewellery/accessories interest"],[/\b(fitness|sportswear|gym|activewear)\b/,"fitness","Fitness interest"],[/\b(editorial|fashion|runway|lookbook)\b/,"fashion","Fashion/editorial interest"],[/\b(commercial|campaign|e-commerce|ecommerce|advert)\b/,"commercial","Commercial-work interest"]];
 for(const [pattern,key,label] of interests){if(pattern.test(text)){if(profile[key]){score++;flags.push("Matches "+label);}else review=true;}}
 if(location){if(/manchester|london|birmingham/i.test(location)){score++;flags.push("Preferred location");}else{review=true;flags.push(/uk|remote/i.test(location)?"Check travel arrangements":"Check travel cost against fee");}}else{review=true;flags.push("Location not specified");}
 if(item.compensation==="Paid")score++;else if(item.compensation==="Unknown"){review=true;flags.push("Compensation not confirmed");}
 if(!item.description||!item.url){review=true;flags.push("Brief or application details need checking");}
 if(unsuitable)return {label:"Not suitable",className:"not-suitable",reason:flags.join(" · ")};
 if(review||score<2)return {label:"Possible match",className:"possible-match",reason:flags.join(" · ")||"Check the full brief before applying"};
 return {label:"Strong match",className:"strong-match",reason:flags.join(" · ")};
}

async function loadDiscoveredOpportunities(){
  try {
    const response = await fetch("data/opportunities.json?updated=" + Date.now(), {cache:"no-store"});
    if(!response.ok) throw new Error("Discovery feed unavailable");
    const feed = await response.json();
    const localItems = loadOpportunities();
    const localById = new Map(localItems.map(item=>[item.id,item]));
    const remoteItems = (feed.opportunities || []).map(item=>{
      const local = localById.get(item.id) || {};
      return {...item, status:local.status || "New", saved:local.saved || false, demo:false};
    });
    const manualItems = localItems.filter(item=>!item.demo && !remoteItems.some(remote=>remote.id===item.id));
    opportunities = remoteItems.concat(manualItems);
    if(!remoteItems.length && !manualItems.length) opportunities = localItems;
    persist();
    const checked = feed.updated_at ? new Date(feed.updated_at).toLocaleString("en-GB",{dateStyle:"medium",timeStyle:"short"}) : "Not checked yet";
    $("#last-updated").textContent = feed.source_count ? "Last source check: " + checked : "No live feeds configured yet";
    render();
  } catch(error) {
    $("#last-updated").textContent = "Discovery feed not available — showing saved data";
  }
}

let currentView = "all";
let currentCategory = "";

function loadOpportunities(){
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : DEMO_OPPORTUNITIES;
  } catch { return DEMO_OPPORTUNITIES; }
}
function persist(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(opportunities)); }
function escapeHtml(value=""){
  return String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
}
function prettyDate(value){
  if(!value) return "Deadline not specified";
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(value+"T12:00:00") : new Date(value);
  return Number.isNaN(date.getTime()) ? "Deadline not specified" : date.toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"});
}
function isFree(item){ return ["TFP","Unpaid"].includes(item.compensation); }
function visibleItems(){
  const query = $("#search").value.trim().toLowerCase();
  const category = currentCategory || $("#category-filter").value;
  const pay = $("#pay-filter").value;
  const location = $("#location-filter").value;
  let items = opportunities.filter(item => {
    const text = [item.title,item.category,item.location,item.source,item.description].join(" ").toLowerCase();
    if(query && !text.includes(query)) return false;
    if(category && item.category !== category) return false;
    if(pay && item.compensation !== pay) return false;
    if(location && item.location !== location && !(location==="Remote / UK-wide" && /uk|remote/i.test(item.location))) return false;
    if(currentView==="saved" && !item.saved) return false;
    if(currentView==="applied" && item.status!=="Applied") return false;
    if(currentView==="new" && item.status!=="New") return false;
    return true;
  });
  const sort = $("#sort-filter").value;
  if(sort==="deadline") items.sort((a,b)=>(a.deadline||"9999").localeCompare(b.deadline||"9999"));
  else if(sort==="title") items.sort((a,b)=>a.title.localeCompare(b.title));
  else items.sort((a,b)=>(b.added||"").localeCompare(a.added||""));
  return items;
}
function render(){
  const saved = opportunities.filter(x=>x.saved).length;
  const applied = opportunities.filter(x=>x.status==="Applied").length;
  $("#stat-total").textContent = opportunities.length;
  $("#stat-free").textContent = opportunities.filter(isFree).length;
  $("#stat-saved").textContent = saved;
  $("#stat-applied").textContent = applied;
  $("#nav-all").textContent = opportunities.length;
  $("#nav-saved").textContent = saved;
  $("#nav-applied").textContent = applied;
  const names = {all:"All opportunities",saved:"Saved opportunities",applied:"Applied opportunities",new:"New finds"};
  $("#breadcrumb-view").textContent = currentCategory || names[currentView];
  $("#page-title").innerHTML = currentCategory ? escapeHtml(currentCategory)+" <em>opportunities.</em>" : currentView==="all" ? 'Find your next <em>opportunity.</em>' : '<em>'+escapeHtml(names[currentView])+'</em>';
  $("#list-title").textContent = currentCategory ? currentCategory+" opportunities" : names[currentView]==="All opportunities" ? "Latest opportunities" : names[currentView];
  const items = visibleItems();
  $("#result-count").textContent = items.length+" result"+(items.length===1?"":"s");
  $("#demo-notice").hidden = !items.some(x=>x.demo);
  $("#profile-prompt").hidden = hasProfile();
  $("#opportunity-list").innerHTML = items.length ? items.map(cardHtml).join("") : '<div class="empty-state"><strong>No opportunities found</strong><p>Try changing your filters, or add an opportunity you found elsewhere.</p></div>';
  document.querySelectorAll(".nav-item[data-view]").forEach(btn=>btn.classList.toggle("active",btn.dataset.view===currentView&&!currentCategory));
  document.querySelectorAll(".category-link").forEach(btn=>btn.classList.toggle("active",btn.dataset.category===currentCategory));
}
function cardHtml(item){
  const payClass = item.compensation==="Paid"?"paid":item.compensation==="TFP"?"tfp":item.compensation==="Unpaid"?"unpaid":"unknown";
  const safeUrl = safeLink(item.url);
  const statusOptions = ["New","Saved","Applied","Expired"];
  const match = hasProfile() ? matchFor(item) : {label:"Profile needed",className:"possible-match",reason:"Create your private profile to see personalised matching."};
  return '<article class="op-card"><div><div class="op-meta"><span class="match-pill '+match.className+'">'+match.label+'</span><span class="tag">'+escapeHtml(item.category)+'</span><span class="tag '+payClass+'">'+escapeHtml(item.compensation||"Unknown")+'</span>'+(item.demo?'<span class="tag sample">Example data</span>':'')+'</div><h3>'+escapeHtml(item.title)+'</h3><div class="op-source">'+escapeHtml(item.source||"Source not specified")+'</div><p class="match-reason">'+escapeHtml(match.reason)+'</p><p class="op-description">'+escapeHtml(item.description||"No additional details provided.")+'</p><div class="op-details"><span>⌖ '+escapeHtml(item.location||"Location TBC")+'</span><span>◷ '+escapeHtml(prettyDate(item.deadline))+'</span></div></div><div class="op-actions"><button class="save-button '+(item.saved?"saved":"")+'" data-save="'+escapeHtml(item.id)+'" aria-label="'+(item.saved?"Remove bookmark":"Save opportunity")+'">'+(item.saved?"♥":"♡")+'</button><select class="status-select" data-status="'+escapeHtml(item.id)+'" aria-label="Application status">'+statusOptions.map(s=>'<option '+(item.status===s?"selected":"")+'>'+s+'</option>').join("")+'</select><a class="apply-link" href="'+escapeHtml(safeUrl)+'" target="_blank" rel="noopener noreferrer">View source ↗</a></div></article>';
}
function safeLink(value){
  try { const url=new URL(value); return ["http:","https:"].includes(url.protocol)?url.href:"#"; } catch { return "#"; }
}
function resetFilters(){ $("#category-filter").value=""; $("#pay-filter").value=""; $("#location-filter").value=""; $("#search").value=""; currentCategory=""; }
function openDialog(){ $("#opportunity-dialog").showModal(); }
$("#profile-open").addEventListener("click",profileFormOpen);
$("#profile-prompt-open").addEventListener("click",profileFormOpen);
$("#profile-close").addEventListener("click",()=>$("#profile-dialog").close());
$("#profile-cancel").addEventListener("click",()=>$("#profile-dialog").close());
$("#profile-form").addEventListener("submit",event=>{
 event.preventDefault();const form=event.currentTarget,values=new FormData(form),next={};
 for(const key of PROFILE_FIELDS){const field=form.elements.namedItem(key);if(field)next[key]=field.type==="checkbox"?field.checked:(values.get(key)||"").trim();}
 profile=next;saveProfile();$("#profile-dialog").close();render();
});
$("#add-open").addEventListener("click",openDialog);
$("#add-open-main").addEventListener("click",openDialog);
$("#add-close").addEventListener("click",()=>$("#opportunity-dialog").close());
$("#add-cancel").addEventListener("click",()=>$("#opportunity-dialog").close());
$("#parse-brief").addEventListener("click",()=>{
 const form=$("#opportunity-form"),raw=form.elements.namedItem("rawBrief").value.trim();
 if(!raw){$("#capture-hint").textContent="Paste some brief text first.";return;}
 const lower=raw.toLowerCase(),lines=raw.split(/\n+/).map(x=>x.trim()).filter(Boolean);
 const titleField=form.elements.namedItem("title");
 if(!titleField.value.trim()&&lines[0])titleField.value=lines[0].replace(/^[@#]+/,"").slice(0,120);
 const categoryField=form.elements.namedItem("category");
 if(/runway|catwalk|fashion week/.test(lower))categoryField.value="Runway";
 else if(/editorial|magazine|photoshoot|photo shoot/.test(lower))categoryField.value="Editorial";
 else if(/campaign|commercial|e-?commerce|brand ambassador|lookbook/.test(lower))categoryField.value="Commercial";
 else if(/fashion|model|modelling|modeling/.test(lower))categoryField.value="Fashion";
 const payField=form.elements.namedItem("compensation");
 if(/expenses (only|covered|paid)|travel expenses|expenses reimbursed/.test(lower))payField.value="Expenses only";
 else if(/\bTFP\b|time for prints?|time for print/i.test(raw))payField.value="TFP";
 else if(/\bunpaid\b|voluntary|volunteer/.test(lower))payField.value="Unpaid";
 else if(/£\s?\d|\bpaid\b|\bfee\b|\brate\b|\bday rate\b/.test(lower))payField.value="Paid";
 const cities=["Manchester","London","Birmingham","Leeds","Liverpool","Bristol","Glasgow","Edinburgh"];
 const found=cities.find(city=>new RegExp("\\b"+city+"\\b","i").test(raw));
 if(found)form.elements.namedItem("location").value=found;
 else if(/remote|UK[- ]wide|nationwide/i.test(raw))form.elements.namedItem("location").value="Remote / UK-wide";
 const dateMatch=raw.match(/(?:deadline|apply by|closes?|closing date)[:\s-]*([0-3]?\d[\/.-][01]?\d[\/.-](?:20)?\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+[0-3]?\d(?:,?\s+20\d{2})?|[0-3]?\d\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})/i);
 if(dateMatch){const rawDate=dateMatch[1],uk=rawDate.match(/^([0-3]?\d)[\/.-]([01]?\d)[\/.-](20\d{2})$/);const parsed=uk?new Date(Number(uk[3]),Number(uk[2])-1,Number(uk[1])):new Date(rawDate);if(!Number.isNaN(parsed.getTime()))form.elements.namedItem("deadline").value=parsed.toISOString().slice(0,10);}
 const linkMatch=raw.match(/https?:\/\/[^\s<>]+/i);if(linkMatch&&!form.elements.namedItem("url").value)form.elements.namedItem("url").value=linkMatch[0].replace(/[),.]+$/,"");
 const instagramMatch=raw.match(/(?:instagram\.com\/|@)([a-z0-9._]{2,30})/i);if(instagramMatch&&!form.elements.namedItem("source").value)form.elements.namedItem("source").value="@"+instagramMatch[1];
 $("#capture-hint").textContent="Details filled where recognisable. Check every field and add the original post/application link before saving.";
});
$("#opportunity-form").addEventListener("submit",event=>{
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const url = safeLink(data.get("url"));
  if(url==="#"){ alert("Please enter a valid http or https application link."); return; }
  opportunities.unshift({id:crypto.randomUUID(),title:data.get("title").trim(),category:data.get("category"),compensation:data.get("compensation"),location:data.get("location").trim()||"Location TBC",deadline:data.get("deadline"),source:data.get("source").trim()||"Manually added",url,description:[data.get("notes").trim(),data.get("rawBrief").trim()].filter(Boolean).join("\n\n"),added:new Date().toISOString().slice(0,10),status:"New",saved:false,demo:false});
  persist(); event.currentTarget.reset(); $("#capture-hint").textContent="We’ll identify likely details for you to review. Nothing is submitted automatically."; $("#opportunity-dialog").close(); currentView="all"; resetFilters(); render();
});
$("#opportunity-list").addEventListener("click",event=>{
  const button=event.target.closest("[data-save]");
  if(!button) return;
  const item=opportunities.find(x=>x.id===button.dataset.save);
  if(item){item.saved=!item.saved;persist();render();}
});
$("#opportunity-list").addEventListener("change",event=>{
  const select=event.target.closest("[data-status]");
  if(!select) return;
  const item=opportunities.find(x=>x.id===select.dataset.status);
  if(item){item.status=select.value;if(select.value==="Saved")item.saved=true;persist();render();}
});
["search","category-filter","pay-filter","location-filter","sort-filter"].forEach(id=>$("#"+id).addEventListener("input",render));
document.querySelectorAll(".nav-item[data-view]").forEach(btn=>btn.addEventListener("click",()=>{currentView=btn.dataset.view;currentCategory="";render();}));
document.querySelectorAll(".category-link").forEach(btn=>btn.addEventListener("click",()=>{currentView="all";currentCategory=btn.dataset.category;$("#category-filter").value="";render();}));
document.addEventListener("keydown",event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="k"){event.preventDefault();$("#search").focus();}});
render();
loadDiscoveredOpportunities();
loadSources();
