# Source Card: sporttery_zqspf

## Identity

- **Website:** China Sports Lottery / 中国竞彩网
- **Target URL:** `https://www.sporttery.cn/jc/jsq/zqspf/index.html`
- **Project owner consent:** The project owner authorized the project team to
  operate this repository and its dedicated browser workflow on 2026-07-11.
  This does not constitute source operator or rights-holder authorization for
  automated collection.
- **Collection mode:** Public-visible page monitoring only. It must not log in,
  read session material, inspect network traffic, or call hidden APIs.
- **Scope:** Public竞彩足球足球胜平负与让球胜平负赛事和奖金信息 only.

## Collection Design

- **Expected update frequency:** Poll no faster than every 60 seconds; do not
  assume a faster cadence without a documented source limit.
- **Selected acquisition method:** The project's dedicated no-login Edge
  browser monitor is the sole planned input for this source. The monitor reads
  the visible source table after one permitted user-equivalent page refresh; it
  does not inspect cookies, network traffic, hidden APIs, or a user's daily
  browser session. Direct HTTP collection is not planned for this source.
- **Login:** Public-visible mode does not log in. A login prompt, CAPTCHA,
  access-control prompt, or account-only content stops collection and requires
  a new source review; P4-02 does not make those prompts permissible.
- **Rendering:** Browser-monitored rendering is the proposed transport for the
  visible page workflow. It does not establish source authorization.
- **Rate limit:** No published numeric limit identified. Use the configured
  per-source limiter and the 60-second minimum until written limits are found.

## Data Contract

- **Candidate fields:** match number, competition, start time, home team, away
  team, handicap, win/draw/loss odds, handicap win/draw/loss odds, sale status,
  update time, and optional public support-rate data.
- **Stable business ID:** Source match number plus game date; if unavailable,
  use the source's published match identifier after documenting its stability.
- **Empty data:** Valid when the page reports no saleable matches for the
  selected date. A structurally invalid response is a parsing failure, not an
  empty result.
- **Permitted failures:** Transient network errors, 429/502/503 under P2-04
  policy, and explicit public-page maintenance notices. CAPTCHA, access-control
  prompts, or login requirements stop collection and require human review.
- **Fixture:** No response body is retained in this documentation task. A
  redacted, authorized fixture is required before any adapter implementation.

## Compliance Review

- **Terms:** The published user agreement states that site content may not be
  copied or used for derivative works without prior authorization from the
  operator or rights holder. Project owner consent is not evidence of that
  source-side authorization. Therefore this source needs an external
  authorization record before public-visible monitoring can be enabled.
- **robots.txt:** Automatic retrieval did not return a readable policy during
  this review. This remains a blocking manual verification point before the
  source-specific P3-04 Adapter is enabled.
- **Browser-monitor boundary:** Selecting the browser monitor as the data
  transport does not waive robots guidance, terms, the authorization scope, or
  rate limits. It changes *how* authorized data enters the project, not whether
  this particular source may be automated.
- **Production eligibility:** The generic P4-01 browser runtime is locally
  accepted. The `sporttery_zqspf` Adapter remains **not approved** until robots
  guidance, the external authorization record, and the approved cadence are
  reconfirmed.

## P3-04 Approval Intake

P3-04 remains blocked until every item in
`docs/operations/source-approval-intake.md` has a non-sensitive human
confirmation. For a source whose published terms and robots guidance clearly
permit public-visible monitoring, an external authorization record is not
required. This source's current terms record requires one.

Do not place authorization documents, account details, cookies, tokens, or a
browser profile in Git. Store any underlying authorization record outside the
repository and provide only its reference, issuer, scope, and review date.

## Alert Thresholds

- Alert after three consecutive source failures.
- Alert when no successful public update occurs for two expected polling
  intervals.
- Alert immediately for 401, 403, CAPTCHA, access-control content, or an
  unexpected login requirement.

## Evidence

- The official target page is indexed as “足球胜平负” and exposes the listed
  public match and odds categories.
- The site user agreement includes copyright and authorization restrictions.
- Review date: 2026-07-11 (Beijing time).
