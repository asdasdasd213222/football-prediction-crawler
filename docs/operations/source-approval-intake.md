# Source Approval Intake

## Purpose

Use this template before enabling a real-source Adapter. It records the
non-sensitive facts needed for P3-04 review. A project owner's permission to
operate a computer, browser, or repository does not replace authorization from
the source operator or rights holder.

Do not send or commit authorization documents, passwords, cookies, access
tokens, personal data, or browser-profile files.

## How To Provide It

Reply in the task conversation with the completed fields below, or have an
authorized reviewer provide the same non-sensitive declaration. Keep the
underlying evidence outside the repository.

## Required Declaration

```text
Source ID: <source_id>

1. Source-side authorization
   - Status: confirmed / unavailable
   - External record reference: <non-secret identifier or location>
   - Issuer or rights holder: <organization or role>
   - Allowed data and purpose: <fields and intended use>
   - Validity: <date range or review date>

2. robots or published automation guidance
   - Reviewed URL or document: <URL or title>
   - Review date (Beijing time): <YYYY-MM-DD>
   - Conclusion: allowed / disallowed / unclear
   - Relevant rule or reviewer rationale: <short summary>

3. Approved cadence
   - Minimum interval: <at least 60 seconds>
   - Allowed time window: <if limited>
   - Basis: <source rule, authorization, or written instruction>

4. Dedicated Edge profile
   - Manual login completed: yes / no / not required
   - Profile is outside the repository: yes / no
   - Credentials, cookies, and profile files are excluded from Git and logs: yes / no
```

## Review Outcome

- `confirmed` requires a source-side authorization record, readable permitted
  automation guidance, and an approved cadence.
- `unavailable` or `unclear` blocks the real-source Adapter and production
  enablement. It does not block mock-server or offline development.
