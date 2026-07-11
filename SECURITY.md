# Security policy

This repository distributes executable Python (community nodes) that runs on users'
machines. We take reports seriously and act on them quickly.

## Reporting a malicious or vulnerable node

**Preferred: open a private security advisory.**
Go to this repository's **Security → Advisories → Report a vulnerability**
(<https://github.com/edwardvaneechoud/flowfile-community-nodes/security/advisories/new>).
A private advisory keeps the details out of public view until a fix or takedown is in
place. Use this for anything that could harm a user who installs the node — data
exfiltration, code execution, credential theft, or a deliberately deceptive node.

**Otherwise: file a _Report a node_ issue.**
If you can't use advisories, open an issue with the **Report a node** form and include the
node id, the version, and what you observed. Please **do not** paste a working exploit into
a public issue — describe the behavior and, if needed, attach evidence privately.

Do not report suspected-malicious nodes only via the normal Discussions/issue channels
without flagging them — use one of the two paths above so a maintainer sees it fast.

## What happens after a report

1. A maintainer triages the report (typically within a day or two).
2. If a node is malicious or dangerously broken, it is added to
   `registry/blocklist.json` (`blocked` for security, `yanked` for a bad version) and, when
   appropriate, removed from `nodes/`.
3. The next `index.json` build carries the blocklist. Because the index is served with a
   short cache, clients see the delisting **within about ten minutes** of the maintainer's
   action.

## Takedown expectations and limits

- **Delisting is fast** (~10 minutes) — a blocked node stops appearing in the browse list
  and the client **refuses to install it**.
- **Already-installed** copies are the user's local files. Removing a node from the registry
  does not reach into installs; users uninstall from within the app. (Runtime blocking of an
  installed-but-now-blocked node is on the roadmap, not guaranteed today.)
- **Historical bytes may persist on CDNs.** Artifacts were once served from commit-pinned,
  immutable CDN URLs (jsDelivr / raw), so old bytes can remain reachable by direct URL even
  after delisting. This is why the client verifies sha256 pins **and refuses to install
  anything on the blocklist** — a blocked node cannot be installed through the app regardless
  of whether its bytes still exist somewhere.

## Scope

This policy covers the registry infrastructure (workflows, scripts, validator config) and
the nodes distributed here. Vulnerabilities in Flowfile itself belong in the
[Flowfile repository](https://github.com/edwardvaneechoud/Flowfile/security).
