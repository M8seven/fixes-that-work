# Facebook Profile Bulk Cleanup: Automated Deletion of Posts, Photos, and Activity via Browser Console Scripts

*Author: Valentino Paulon*
*Technical Document — Social Media Privacy & Account Management*

---

## Executive Summary

This document addresses the problem of bulk-deleting content from a personal Facebook profile — a task that Facebook deliberately makes difficult through its UI and does not support through its API for personal accounts.

Key findings:

- Facebook's Graph API **does not allow** deletion of personal profile posts. The `DELETE /{post-id}` endpoint only works for content created by the requesting app, making programmatic cleanup impossible through official channels.
- All existing third-party tools (Redact.dev, Social Erase, etc.) are either **paid services** or **unmaintained browser extensions** that break with every Facebook UI update.
- Facebook's built-in "Manage Activity" page allows bulk selection but fails on many content types, forces manual interaction, and provides no automation path.
- The solution documented here uses **browser console JavaScript** that interacts directly with Facebook's rendered DOM, automating the click-wait-confirm cycle that a human would perform manually.
- Two scripts are provided: one for **Activity Log posts** and one for **profile photos**. Each handles Facebook's inconsistent menu structures (some items show "Delete", others "Move to trash", others only "Add to profile"). The approach is extensible to other content types (comments, reactions, etc.) by adapting the selectors.

All scripts run in-browser, require no installation, no API keys, no third-party access, and work on the user's authenticated session.

---

## 1. Problem Statement

### 1.1 Scenario

A user wants to clean their Facebook profile — delete all posts, photos, and activity — either for privacy reasons, to repurpose the account for a business page, or simply to start fresh.

### 1.2 Why This Is Hard

Facebook has a commercial interest in retaining user content. The platform provides:

- **No bulk delete API** for personal accounts
- **No "delete all" button** in the UI
- **Manual deletion only**: each post requires 3-4 clicks (menu → delete → confirm)
- **Inconsistent menu options**: depending on content type, the delete option may be labeled "Delete", "Move to trash", or may not exist at all (replaced by "Add to profile" or "Hide from profile")
- **Content type fragmentation**: posts, photos, videos, comments, reactions, check-ins, and group posts are all managed in separate UI sections

### 1.3 Why Existing Solutions Fail

| Solution | Problem |
|----------|---------|
| Facebook Graph API | Cannot delete personal posts — only app-created content |
| Redact.dev | Free tier limited to 30 days; full cleanup requires paid subscription |
| Social Erase (Chrome extension) | Requires Facebook in English (US); breaks with UI changes |
| DeleteFB (Python/Selenium) | Unmaintained since 2021; incompatible with current Facebook DOM |
| facebook-post-bulk-deleter (GitHub) | Requires manual aria-label discovery; single-purpose (posts only) |
| Manual deletion | Feasible for 10-20 items; impractical for hundreds or thousands |

---

## 2. Solution Architecture

### 2.1 Approach

The scripts operate by automating the same UI interactions a human would perform:

1. **Locate** the action button for each content item (identified by `aria-label`)
2. **Click** to open the context menu
3. **Find** the delete/trash option in the menu
4. **Click** the delete option
5. **Wait** for the confirmation dialog
6. **Confirm** the deletion
7. **Wait** for the page to update
8. **Repeat** for the next item, scrolling as needed

### 2.2 Key Technical Challenges

**Inconsistent menu labels**: Facebook uses different labels depending on content type and visibility state:

| Content State | Menu Option | Confirmation Dialog |
|--------------|-------------|-------------------|
| Regular post | "Delete" | "Delete?" → "Delete" |
| Hidden post | "Move to trash" | "Move to Trash?" → "Move to Trash" |
| Profile update | "Add to profile" only | No delete available |
| Photo | "Delete photo" | "Delete Photo" → "Delete" |

**Dynamic DOM**: Facebook uses obfuscated CSS class names that change with every deployment. The scripts rely on **semantic attributes** (`role`, `aria-label`) rather than class names, making them resilient to Facebook's frequent UI updates.

**Rate limiting**: Clicking too fast causes Facebook's UI to fall behind. Each script includes configurable delays between actions.

**Infinite scroll**: Content loads dynamically as the user scrolls. Scripts must scroll periodically to load additional items.

**Background tab throttling**: Chrome (and other Chromium-based browsers) aggressively throttle JavaScript timers in background tabs — after 5 minutes of inactivity, timers are limited to once per minute. This causes the scripts to freeze when the user switches to another tab. The scripts include an **anti-throttle mechanism**: a near-silent audio oscillator (`gain: 0.001`) that keeps the tab classified as "audible", preventing Chrome from throttling it. This allows the scripts to run unattended while the user works in other tabs.

---

## 3. Prerequisites

### 3.1 Browser Support

| Browser | Console Shortcut | Paste Restriction |
|---------|-----------------|-------------------|
| Chrome (macOS) | `Cmd + Option + J` | Type `allow pasting` first |
| Chrome (Windows/Linux) | `Ctrl + Shift + J` | Type `allow pasting` first |
| Firefox (macOS) | `Cmd + Option + K` | None |
| Firefox (Windows/Linux) | `Ctrl + Shift + K` | None |
| Safari (macOS) | `Cmd + Option + C` (enable Developer menu first) | None |
| Edge (Windows) | `Ctrl + Shift + J` | Type `allow pasting` first |

### 3.2 Chrome Paste Restriction

Chrome blocks pasting into the console by default with a "Stop!" warning about self-XSS attacks. To bypass:

1. Open the Console
2. Type `allow pasting` manually (not pasted) and press Enter
3. You will see a `SyntaxError` — this is normal
4. You can now paste code

**Alternative (recommended)**: Use **Snippets** instead of the Console:

1. Open DevTools → **Sources** tab → **Snippets** (left panel)
2. Click **+ New snippet**
3. Paste the script
4. Right-click the snippet → **Run**

Snippets bypass the paste restriction entirely and can be saved for reuse.

### 3.3 Facebook Language

The scripts handle both **English** and **Italian** menu labels. If your Facebook is in another language, you will need to add the corresponding translations to the text-matching arrays in the scripts (see [Section 6: Customization](#6-customization)).

---

## 4. Scripts

### 4.1 Script 1: Delete Activity Log Posts

**Target page**: Activity Log → Your Facebook activity → Posts → Your posts, photos and videos

**URL**: `https://www.facebook.com/allactivity` → expand "Your Facebook activity" → "Posts"

**What it deletes**: All posts visible in the Activity Log that have a "Delete" or "Move to trash" option.

**What it skips**: Items that only have "Add to profile" (these are already hidden and cannot be deleted from the Activity Log).

```javascript
(async function() {
  // Anti-throttle: prevents Chrome from pausing the script in background tabs
  var audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  var oscillator = audioCtx.createOscillator();
  var gain = audioCtx.createGain();
  gain.gain.value = 0.001;
  oscillator.connect(gain);
  gain.connect(audioCtx.destination);
  oscillator.start();

  var sleep = function(ms) { return new Promise(function(r) { setTimeout(r, ms); }); };
  var deleted = 0;
  var skip = 0;

  while(true) {
    var btns = document.querySelectorAll('div[aria-label="More options"]');
    if(skip >= btns.length) {
      window.scrollBy(0, 500);
      await sleep(4000);
      var newBtns = document.querySelectorAll('div[aria-label="More options"]');
      if(skip >= newBtns.length) { console.log("Done! Deleted: " + deleted); break; }
      btns = newBtns;
    }

    var btn = btns[skip];
    if(!btn) { console.log("Done! Deleted: " + deleted); break; }

    btn.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(1000);

    btn.click();
    await sleep(2000);

    var found = false;
    var menuItems = document.querySelectorAll('div[role="menuitem"], div[role="option"]');
    for(var i = 0; i < menuItems.length; i++) {
      var text = (menuItems[i].textContent || "").trim().toLowerCase();
      if(text === "delete" || text === "elimina" || text === "move to trash" || text === "sposta nel cestino") {
        menuItems[i].click();
        found = true;
        break;
      }
    }

    if(!found) {
      document.body.click();
      await sleep(500);
      skip++;
      console.log("No delete option, skipping (" + skip + ")");
      continue;
    }

    await sleep(3000);

    var dialog = document.querySelector('div[role="dialog"]');
    if(dialog) {
      var dialogBtns = dialog.querySelectorAll('div[role="button"], button');
      for(var j = 0; j < dialogBtns.length; j++) {
        var btnText = (dialogBtns[j].textContent || "").trim().toLowerCase();
        if(btnText === "delete" || btnText === "elimina" || btnText === "move to trash" || btnText === "sposta nel cestino" || btnText === "confirm" || btnText === "conferma") {
          dialogBtns[j].click();
          break;
        }
      }
    }

    deleted++;
    console.log("Deleted #" + deleted);
    await sleep(4000);
  }
})();
```

**Expected console output**:
```
No delete option, skipping (1)
No delete option, skipping (2)
Deleted #1
Deleted #2
Deleted #3
...
Done! Deleted: 47
```

### 4.2 Script 2: Delete Photos

**Target page**: Your profile → Photos → **Your photos** tab

**URL**: `https://www.facebook.com/{your-username}/photos_by`

**What it deletes**: All photos in the "Your photos" section. Each photo deletion also deletes the associated post.

**Important**: Make sure you are on the **"Your photos"** tab, not "Photos of You".

```javascript
(async function() {
  // Anti-throttle: prevents Chrome from pausing the script in background tabs
  var audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  var oscillator = audioCtx.createOscillator();
  var gain = audioCtx.createGain();
  gain.gain.value = 0.001;
  oscillator.connect(gain);
  gain.connect(audioCtx.destination);
  oscillator.start();

  var sleep = function(ms) { return new Promise(function(r) { setTimeout(r, ms); }); };
  var deleted = 0;
  var maxLoop = 500;

  for(var loop = 0; loop < maxLoop; loop++) {
    var pencils = document.querySelectorAll('div[aria-label="More options for this photo"]');

    if(pencils.length === 0) {
      window.scrollBy(0, 500);
      await sleep(4000);
      pencils = document.querySelectorAll('div[aria-label="More options for this photo"]');
      if(pencils.length === 0) { console.log("Done! Photos deleted: " + deleted); break; }
    }

    var pencil = pencils[0];
    if(!pencil) { console.log("Done! Photos deleted: " + deleted); break; }

    pencil.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(1500);

    pencil.click();
    await sleep(2500);

    var found = false;
    var menuItems = document.querySelectorAll('div[role="menuitem"]');
    for(var i = 0; i < menuItems.length; i++) {
      var text = (menuItems[i].textContent || "").trim().toLowerCase();
      if(text.includes("delete photo") || text.includes("elimina foto")) {
        menuItems[i].click();
        found = true;
        break;
      }
    }

    if(!found) {
      var closeBtn = document.querySelector('div[aria-label="Close"], div[aria-label="Chiudi"]');
      if(closeBtn) closeBtn.click();
      else document.body.click();
      await sleep(1000);
      console.log("Delete photo not found, skipping...");
      continue;
    }

    await sleep(3000);

    var clicked = false;
    var allBtns = document.querySelectorAll('div[role="button"], button, span[role="button"], a[role="button"]');
    for(var j = allBtns.length - 1; j >= 0; j--) {
      var btnText = (allBtns[j].textContent || "").trim();
      if(btnText === "Delete" || btnText === "Elimina") {
        allBtns[j].click();
        clicked = true;
        break;
      }
    }

    if(!clicked) {
      var allElements = document.querySelectorAll('div[role="button"], button');
      for(var k = allElements.length - 1; k >= 0; k--) {
        var inner = (allElements[k].innerText || "").trim();
        if(inner === "Delete" || inner === "Elimina") {
          allElements[k].click();
          clicked = true;
          break;
        }
      }
    }

    if(clicked) {
      deleted++;
      console.log("Photo deleted #" + deleted);
    } else {
      console.log("Confirmation not found");
      var closeBtn = document.querySelector('div[aria-label="Close"], div[aria-label="Chiudi"]');
      if(closeBtn) closeBtn.click();
    }

    await sleep(5000);
  }

  console.log("Script finished. Photos deleted: " + deleted);
})();
```

### 4.3 How to Find aria-labels (When Scripts Stop Working)

Facebook may change `aria-label` values in future updates. To discover the current labels:

1. Navigate to the target page (Activity Log or Photos)
2. Open DevTools (see [Section 3.1](#31-browser-support))
3. Right-click on the target button (three dots, pencil icon, etc.) → **Inspect**
4. In the Elements panel, look for `aria-label="..."` on the highlighted element or its parent

Alternatively, run this in the console to list all labeled elements:

```javascript
document.querySelectorAll('[aria-label]').forEach(function(el) {
  console.log("LABEL:", el.getAttribute('aria-label'), "| ROLE:", el.getAttribute('role'));
});
```

Update the `querySelectorAll('div[aria-label="..."]')` strings in the scripts with the new values.

---

## 5. Execution Guide

### 5.1 Step-by-Step: Deleting Posts

1. Go to `https://www.facebook.com/allactivity`
2. Click **"Your Facebook activity"** (expand the section)
3. Click **"Posts"** → **"Your posts, photos and videos"**
4. Open DevTools → Sources → Snippets → New snippet
5. Paste **Script 1** → Right-click → Run
6. Watch the console for progress
7. If the script stops (page didn't load in time), reload the page and run again — it will continue from where the remaining content starts

### 5.2 Step-by-Step: Deleting Photos

1. Go to your profile → **Photos** → **"Your photos"** tab
2. Open DevTools → Sources → Snippets → New snippet
3. Paste **Script 2** → Right-click → Run
4. Watch the console for progress

### 5.3 Stopping a Script

To stop a running script at any time:

- **Reload the page** (`Cmd+R` / `Ctrl+R` / `F5`) — this immediately kills the script

---

## 6. Customization

### 6.1 Adjusting Speed

If the script runs too fast for your connection, increase the `sleep()` values (in milliseconds):

```javascript
await sleep(4000);  // 4 seconds — increase to 6000 or 8000 for slow connections
```

If the script is too slow, decrease them — but don't go below `1000` or Facebook's UI won't keep up.

### 6.2 Adding Languages

The scripts match menu text in English and Italian. To add another language, find the text-matching sections and add your translations:

```javascript
// Example: adding French and German
if(text === "delete" || text === "elimina" || text === "supprimer" || text === "loschen" ||
   text === "move to trash" || text === "sposta nel cestino" || text === "mettre a la corbeille") {
```

### 6.3 Handling New Menu Options

If Facebook adds new menu structures, the diagnostic approach is always the same:

1. Click the action button manually
2. Inspect the menu items that appear
3. Note the exact text and the element's `role` attribute
4. Update the script's selectors and text-matching accordingly

---

## 7. Limitations

- **"Add to profile" items cannot be deleted** from the Activity Log. These are posts by other people on your timeline that are already hidden. They can only be managed from the original poster's side.
- **Profile pictures and cover photos** may require separate handling through the Albums section.
- **Facebook may rate-limit** rapid deletions. If the script starts failing after many successful deletions, wait 10-15 minutes and restart.
- **DOM structure changes** with Facebook updates. The scripts rely on `aria-label` attributes which are more stable than CSS classes, but they can still change. See [Section 4.3](#43-how-to-find-aria-labels-when-scripts-stop-working) for how to adapt.
- **Content in Trash** is automatically deleted after 30 days. To delete immediately, go to Activity Log → Trash → select all → Delete permanently.

---

## 8. Comparison with Alternatives

| Feature | This Solution | Redact.dev | Social Erase | Manual |
|---------|:------------:|:----------:|:------------:|:------:|
| Cost | Free | $8+/month | Free (limited) | Free |
| Posts deletion | Yes | Yes | Yes | Yes |
| Photos deletion | Yes | Yes | Partial | Yes |
| No installation | Yes | No (app) | No (extension) | Yes |
| Works offline | N/A | No | N/A | N/A |
| Handles "Move to trash" | Yes | Yes | No | Yes |
| Customizable | Yes (source) | No | No | N/A |
| Survives FB updates | Adaptable | Vendor-dependent | Often breaks | Always |
| Speed (100 items) | ~8 minutes | ~5 minutes | ~10 minutes | ~2 hours |

---

## License

MIT

## Disclaimer

This tool automates actions that a user can perform manually through Facebook's standard interface. It does not bypass any authentication, access control, or security mechanism. It does not access other users' data. It operates entirely within the user's authenticated browser session on their own account.

All testing was conducted on the author's own Facebook account. No unauthorized access to third-party systems was performed.
