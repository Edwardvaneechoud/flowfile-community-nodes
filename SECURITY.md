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
3. The next `index.json` build carries the blocklist: a blocked node is delisted
   entirely, and a yanked version is delisted until the author publishes a newer one.
   Clients see the delisting on their next index fetch — immediately when a user
   refreshes the browse tab, and **within about an hour** otherwise (the app caches the
   index for an hour by default, `FLOWFILE_COMMUNITY_CACHE_TTL`).

## Takedown expectations and limits

- **Delisting lands on the next index fetch** — minutes for anyone who refreshes, up to
  about an hour for idle clients. A blocked or yanked node stops appearing in the browse
  list and the client **refuses to install it**.
- **Already-installed** copies are the user's local files. Removing a node from the registry
  does not reach into installs; the app shows a warning banner with an uninstall shortcut
  for an installed node that was later blocked or yanked, but the user uninstalls it
  themselves. (Runtime blocking of an installed-but-now-blocked node is on the roadmap,
  not guaranteed today.)
- **Historical bytes may persist on CDNs.** Artifacts are served from commit-pinned,
  immutable CDN URLs (jsDelivr / raw), so old bytes can remain reachable by direct URL even
  after delisting. This is why the client verifies sha256 pins **and refuses to install
  anything on the blocklist** — a blocked node cannot be installed through the app regardless
  of whether its bytes still exist somewhere.
- **Pins are fail-closed for what executes.** A sha256 mismatch on the node file or icon
  aborts the install; screenshots and the README are cosmetic and skipped on mismatch
  rather than failing the install.
- **The index itself is trusted via TLS to this repository's `main` branch** — it is not
  signed. Write access to `main` is the real boundary, which is exactly the "merge button
  is the security boundary" model: protect the repo and you protect the pins.

## Scope

This policy covers the registry infrastructure (workflows, scripts, validator config) and
the nodes distributed here. Vulnerabilities in Flowfile itself belong in the
[Flowfile repository](https://github.com/edwardvaneechoud/Flowfile/security).
