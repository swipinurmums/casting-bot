/**
 * Modelling Opportunity Radar — Gmail intake bridge
 *
 * Reads only messages carrying the Gmail label "Radar/Intake" and publishes
 * minimal lead metadata (never email bodies) to data/email-leads.json.
 *
 * Configure Script Properties:
 *   GITHUB_TOKEN       Fine-grained PAT, Contents: Read and write, this repo only
 *   GITHUB_REPOSITORY  swipinurmums/casting-bot
 *   GITHUB_BRANCH      main
 *
 * Run setup() once, then installTrigger() once.
 */
const INTAKE_LABEL = "Radar/Intake";
const PROCESSED_LABEL = "Radar/Processed";
const OUTPUT_PATH = "data/email-leads.json";
const MAX_THREADS_PER_RUN = 30;

function setup() {
  GmailApp.getUserLabelByName(INTAKE_LABEL) || GmailApp.createLabel(INTAKE_LABEL);
  GmailApp.getUserLabelByName(PROCESSED_LABEL) || GmailApp.createLabel(PROCESSED_LABEL);
  Logger.log("Labels ready. Create a Gmail filter to apply Radar/Intake to platform alerts.");
}

function installTrigger() {
  // Avoid creating duplicate time-based triggers.
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === "publishEmailLeads")
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("publishEmailLeads").timeBased().everyHours(1).create();
  Logger.log("Hourly intake trigger installed.");
}

function publishEmailLeads() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty("GITHUB_TOKEN");
  const repo = props.getProperty("GITHUB_REPOSITORY") || "swipinurmums/casting-bot";
  const branch = props.getProperty("GITHUB_BRANCH") || "main";
  if (!token) throw new Error("Missing GITHUB_TOKEN in Script Properties.");

  const intake = GmailApp.getUserLabelByName(INTAKE_LABEL) || GmailApp.createLabel(INTAKE_LABEL);
  const processed = GmailApp.getUserLabelByName(PROCESSED_LABEL) || GmailApp.createLabel(PROCESSED_LABEL);
  const threads = GmailApp.search('label:"' + INTAKE_LABEL + '" -label:"' + PROCESSED_LABEL + '"', 0, MAX_THREADS_PER_RUN);
  if (!threads.length) {
    Logger.log("No new labelled email threads.");
    return;
  }

  const leads = [];
  threads.forEach(thread => {
    thread.getMessages().forEach(message => {
      const from = message.getFrom() || "";
      const subject = message.getSubject() || "(no subject)";
      const date = message.getDate().toISOString();
      const body = message.getPlainBody() || "";
      const html = message.getBody() || "";
      const links = extractLinks(body + "\n" + html).slice(0, 8);
      const host = (from.match(/@([^>\s]+)/) || [,"unknown"])[1].toLowerCase();
      const source = classifySource(host, from);
      const rawId = message.getId();
      const digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, rawId);
      const id = digest.map(b => ('0' + ((b + 256) % 256).toString(16)).slice(-2)).join('').slice(0, 20);
      leads.push({
        id: "email-" + id,
        title: subject.slice(0, 180),
        source: source,
        sender_domain: host,
        received_at: date,
        source_url: links[0] || "",
        links: links,
        collection_method: "email_notification",
        review_status: "needs_review",
        compensation: "Unknown",
        application_method: "Open the original casting link and verify eligibility, fee, deadline and application route",
        status: "New",
        saved: false,
        demo: false
      });
    });
    // Only mark a thread processed after the repository update succeeds.
  });

  const path = OUTPUT_PATH;
  const api = "https://api.github.com/repos/" + repo + "/contents/" + path;
  const headers = {
    Authorization: "Bearer " + token,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
  };
  const current = UrlFetchApp.fetch(api + "?ref=" + encodeURIComponent(branch), {
    method: "get", headers: headers, muteHttpExceptions: true
  });
  let existing = { version: 1, updated_at: null, leads: [] };
  let sha = null;
  if (current.getResponseCode() === 200) {
    const file = JSON.parse(current.getContentText());
    sha = file.sha;
    existing = JSON.parse(Utilities.newBlob(Utilities.base64Decode(file.content.replace(/\n/g, ""))).getDataAsString());
  } else if (current.getResponseCode() !== 404) {
    throw new Error("GitHub read failed (" + current.getResponseCode() + "): " + current.getContentText().slice(0, 500));
  }

  const byId = {};
  (existing.leads || []).forEach(item => byId[item.id] = item);
  leads.forEach(item => byId[item.id] = item);
  const output = {
    version: 1,
    updated_at: new Date().toISOString(),
    leads: Object.values(byId).sort((a, b) => b.received_at.localeCompare(a.received_at)).slice(0, 500)
  };
  const encoded = Utilities.base64Encode(Utilities.newBlob(JSON.stringify(output, null, 2) + "\n").getBytes());
  const payload = { message: "Import casting notification leads", content: encoded, branch: branch };
  if (sha) payload.sha = sha;
  const write = UrlFetchApp.fetch(api, {
    method: "put", headers: headers, contentType: "application/json",
    payload: JSON.stringify(payload), muteHttpExceptions: true
  });
  if (write.getResponseCode() < 200 || write.getResponseCode() >= 300) {
    throw new Error("GitHub publish failed (" + write.getResponseCode() + "): " + write.getContentText().slice(0, 500));
  }

  // Mark processed only after successful publish.
  threads.forEach(thread => thread.addLabel(processed));
  Logger.log("Published " + leads.length + " email lead(s) from " + threads.length + " thread(s).");
}

function classifySource(host, from) {
  const value = (host + " " + from).toLowerCase();
  if (value.indexOf("backstage") !== -1) return "Backstage";
  if (value.indexOf("talenttalks") !== -1) return "Talent Talks";
  if (value.indexOf("modelsdirect") !== -1) return "Models Direct";
  return "Email notification";
}

function extractLinks(text) {
  const found = text.match(/https?:\/\/[^\s"'<>]+/gi) || [];
  const seen = {};
  return found.map(url => url.replace(/&amp;/g, "&").replace(/[),.;\]]+$/, ""))
    .filter(url => {
      const lower = url.toLowerCase();
      if (/unsubscribe|preferences|privacy|facebook\.com|instagram\.com\/accounts\/|google\.com\/url\?/.test(lower)) return false;
      if (seen[url]) return false;
      seen[url] = true;
      return true;
    });
}
