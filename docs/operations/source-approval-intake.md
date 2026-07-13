# Source Approval Intake

## Purpose

Use this template before enabling a real-source Adapter. It records only the
non-sensitive enablement state for public-visible monitoring. The default mode
is a no-login, user-equivalent page refresh that reads only configured visible
fields. It never reads session material, network traffic, or hidden APIs.

A project owner's permission to operate a computer, browser, or repository does
not by itself approve a source. Detailed review material remains outside the
repository; this document retains only the resulting status and reference.

Do not send or commit authorization documents, passwords, cookies, access
tokens, personal data, or browser-profile files.

## How To Provide It

Reply in the task conversation with the completed fields below, or have an
authorized reviewer provide the same non-sensitive declaration. Keep the
underlying evidence outside the repository.

## Required Declaration

```text
Source ID: <source_id>

1. External enablement review
   - Status: approved / not approved / pending
   - Review date (Beijing time): <YYYY-MM-DD>
   - External record reference: <non-secret identifier or location>
   - Reviewer role: <organization or role>

2. Public-visible page scope
   - Page is public and needs no login: yes / no
   - User-equivalent action: <for example, one visible refresh>
   - Visible fields to retain: <specific fields only>
   - No cookies, network traffic, hidden APIs, or account data are read: yes / no

3. Approved cadence
   - Minimum interval: <at least 60 seconds>
   - Allowed time window: <if limited>
   - Approval reference: <same external reference or another non-secret reference>

4. Dedicated no-login Edge profile
   - Manual login completed: not required
   - Profile is outside the repository: yes / no
   - Credentials, cookies, and profile files are excluded from Git and logs: yes / no

```

## Review Outcome

- A source is eligible only when its external enablement status is `approved`,
  the page is public without login, and its cadence is approved.
- `not approved` or `pending` blocks the real-source Adapter and production
  enablement. This does not block mock-server or offline development.
