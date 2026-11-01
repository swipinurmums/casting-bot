# Gmail email intake (Google Apps Script)

This is a small, user-authorised bridge between your dedicated Gmail inbox and the public opportunity feed. It publishes **email subject, sender domain, received date and links only**. It does not publish message bodies or attachments.

## 1. Create a GitHub token

1. In GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained tokens**.
2. Generate a token restricted to **Only select repositories → swipinurmums/casting-bot**.
3. Under Repository permissions, grant **Contents: Read and write**. No other permissions are needed.
4. Copy the token. Treat it like a password; do not paste it into this repository or into a chat.

## 2. Create the Apps Script

1. Sign into the dedicated Gmail account, `aronsnonsense@gmail.com`.
2. Open [script.google.com](https://script.google.com/) and create a new project.
3. Copy the contents of `integrations/google-apps-script/Code.gs` into the editor and save.
4. In **Project Settings → Script properties**, add:
   - `GITHUB_TOKEN` = the fine-grained token from step 1
   - `GITHUB_REPOSITORY` = `swipinurmums/casting-bot`
   - `GITHUB_BRANCH` = `main`

## 3. Authorise and initialise

1. Select `setup` in the function dropdown and click Run.
2. Review Google's permission prompt. The script needs Gmail read/label access and permission to make HTTPS requests to GitHub.
3. Then select `installTrigger` and click Run. This creates an hourly trigger.

## 4. Route platform alerts into the intake label

In Gmail, create a filter for the platform notification sender addresses once the first real emails arrive. Choose **Apply the label → Radar/Intake**. Do not label unrelated personal mail. The script only reads threads with this label.

The script marks successfully published threads with `Radar/Processed` so they are not imported again. If a thread is labelled after it was processed, remove that label to reprocess it.

## 5. Test safely

Send a test email to the dedicated inbox, label it `Radar/Intake`, then run `publishEmailLeads` manually from Apps Script. Check that `data/email-leads.json` appears in the repository. The record should contain metadata and links, not the email body.

## Important limitations

- This is a metadata/link intake stage, **not yet a reliable casting-brief parser**. Every record is marked `needs_review` and compensation stays `Unknown`.
- Once we have genuine Backstage, Talent Talks and Models Direct notification examples, we can write source-specific parsers and improve link selection.
- The JSON file is in a public repository. Do not route private correspondence or unrelated email into `Radar/Intake`.
- Apps Script runs under your Google account. You can inspect, pause or delete its trigger in Apps Script → Triggers, and revoke Google access from your Google Account security settings.
- GitHub token is stored in Apps Script Script Properties, not in the repo. Rotate/revoke it if exposed.
