# Source Approval Intake

## Purpose

Use this template before enabling a real-source Adapter. It records the
non-sensitive facts needed for P3-04 review of public-visible monitoring. The
default mode is a no-login, user-equivalent page refresh that reads only the
configured visible fields. It never reads session material, network traffic, or
hidden APIs.

A project owner's permission to operate a computer, browser, or repository does
not override published source rules. External source-side authorization is
required only when the published terms or robots guidance require it, or when
their public-monitoring position is unclear.

Do not send or commit authorization documents, passwords, cookies, access
tokens, personal data, or browser-profile files.

## How To Provide It

Reply in the task conversation with the completed fields below, or have an
authorized reviewer provide the same non-sensitive declaration. Keep the
underlying evidence outside the repository.

## Required Declaration

```text
Source ID: <source_id>

1. Public-visible page scope
   - Page is public and needs no login: yes / no
   - User-equivalent action: <for example, one visible refresh>
   - Visible fields to retain: <specific fields only>
   - No cookies, network traffic, hidden APIs, or account data are read: yes / no

2. robots or published automation guidance
   - Reviewed URL or document: <URL or title>
   - Review date (Beijing time): <YYYY-MM-DD>
   - Terms conclusion for public-visible monitoring: allowed / disallowed / unclear
   - robots conclusion: allowed / disallowed / unclear
   - Relevant rule or reviewer rationale: <short summary>

3. Approved cadence
   - Minimum interval: <at least 60 seconds>
   - Allowed time window: <if limited>
   - Basis: <source rule, authorization, or written instruction>

4. Dedicated no-login Edge profile
   - Manual login completed: not required
   - Profile is outside the repository: yes / no
   - Credentials, cookies, and profile files are excluded from Git and logs: yes / no

5. Conditional external authorization
   - Required by published rules: yes / no / unclear
   - If yes or unclear, status: confirmed / unavailable
   - External record reference: <non-secret identifier or location>
   - Issuer or rights holder: <organization or role>
   - Allowed data, purpose, and validity: <short summary>
```

## Review Outcome

- A source is eligible only when the page is public without login, the visible
  monitoring action is permitted by terms and robots guidance, and its cadence
  is approved. If published rules require authorization, an external record is
  additionally required.
- Any required condition that is `disallowed`, `unavailable`, or `unclear`
  blocks the real-source Adapter and production enablement. An external
  authorization status is required only when published rules require it or do
  not state a clear public-monitoring position. This does not block mock-server
  or offline development.
