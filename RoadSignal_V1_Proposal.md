# Project RoadSignal V1 — Vendor Proposal

| | |
|---|---|
| **RFP Reference** | RS-V1-003 |
| **Prepared for** | Mr. Patel \| +61 403786083 |
| **Date** | 26 August 2026 |
| **Classification** | Commercial in Confidence |
| **Currency** | All amounts in AUD excluding GST |

---

# 1. Executive Summary

RoadSignal V1 is a trust-and-safety product system — not simply a QR-code messaging app. It creates a controlled communication layer between a vehicle and a member of the public while keeping both parties' personal contact details private. The most important product challenge is balancing reachability with protection against stalking, false plate claims, harassment, bulk plate enumeration and unsafe use while driving.

**Why this matters financially:** Getting privacy, abuse prevention, identity verification, messaging architecture and trust systems wrong in production is far more expensive than building them correctly in V1. Regulatory penalties under the Privacy Act 1988, app-store removal for safety failures, and the reputational cost of a stalking or harassment incident on a vehicle-contact platform would exceed the V1 build cost several times over. Our proposal invests in getting the trust architecture right the first time.


---

# 2. Understanding of RoadSignal

## 2.1 The problem

A vehicle is a visible, location-bound object, but its owner is usually unreachable. A public phone number solves reachability at the cost of privacy. Plate-based messaging solves discovery at the cost of new abuse vectors. RoadSignal must therefore treat the vehicle identifier as sensitive routing data, not as a social username.

## 2.2 The core engineering challenges

1. **Privacy-by-structure** — PII constraints enforced by architecture, not application-level discipline.
2. **Anti-abuse at the protocol level** — plate enumeration, flood attacks, and false claims caught before they reach recipients.
3. **Minimal-friction discovery** — QR → alert flow works on any device, under 30 seconds, zero installation.
4. **Auditable trust operations** — every moderation action, access decision, and data access event produces a verifiable audit trail.

## 2.3 What we are NOT building

- An emergency dispatch system or replacement for 000
- A social network, driver ratings platform,
- A vehicle tracking or surveillance tool
- An open messaging platform with freeform chat
- A government registration database integration

---

# 3. Proposed Product System

## 3.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ROAD SIGNAL V1 — SYSTEM ARCHITECTURE          │
└─────────────────────────────────────────────────────────────────┘

  ROAD USER (Any Device — No Install Required)
         │ QR Scan or Plate Lookup
         ▼
┌────────────────────────────────────────┐
│         DISCOVERY API GATEWAY           │
│  Token Verification · Rate Limiter     │
│  Anti-Enumeration · Device Check       │
└───────────────────┬────────────────────┘
                    ▼
┌────────────────────────────────────────┐
│          RELAY ENGINE                   │
│  AES-256 Encrypt · Content Validation  │
│  Template Enforcement · Multi-Channel  │
└──────────┬──────────┬──────────┬───────┘
           ▼          ▼          ▼
        Push(FCM)   SMS(Twilio) Email(SendGrid)
                    │
                    ▼
  ┌────────────────────────────────────┐
  │  OWNER DEVICE                      │
  │  Notification → Canned Reply       │
  │  Expiring Token · No PII Outbound  │
  └────────────────────────────────────┘

  ┌────────────────────────────────────┐
  │  ADMIN PORTAL (RBAC)               │
  │  Cases · Audit · Verification      │
  │  Moderation · Abuse Dashboards     │
  └────────────────────────────────────┘

  ┌────────────────────────────────────────────────────┐
  │  GOVERNANCE & SAFETY LAYER                          │
  │  CapabilityGate (7-dim) · Anti-Abuse Pipeline       │
  │  Content Moderation · Rate Limiter · Audit Ledger   │
  └────────────────────────────────────────────────────┘
```

## 3.2 Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Mobile | Flutter (single codebase) | iOS + Android from one project |
| Public Web | React (responsive) | QR landing pages, owner portal |
| Backend API | Python (FastAPI) | Async, Pydantic validation, OpenAPI spec |
| Admin Portal | React + RBAC middleware | Case management, audit viewer |
| Database | PostgreSQL + pgcrypto | Encrypted columns, row-level security |
| Cache/Rate Limit | Redis | Sliding-window limits, session tokens |
| Queue | Celery + Redis | Async notification dispatch |
| Push | FCM + APNs | Cross-platform push |
| Hosting | AWS ap-southeast-2 | Australian data residency |
| Monitoring | CloudWatch + custom health API | Uptime, latency, abuse signals |

## 3.3 What each phase delivers

| Phase | Weeks | What ships |
|---|---|---|
| **1 — Foundation** | 1–4 | Tag lifecycle, vehicle ownership verification, QR discovery API, rate limiting, anti-enumeration, database, encryption, audit logs |
| **2 — Relay & Messaging** | 5–8 | Alert pipeline, canned replies, push/SMS/email notifications, content type enforcement, expiring tokens |
| **3 — Safety & Moderation** | 9–12 | Conjunctive capability gates, multi-perspective abuse detection, case management, block/report, pattern detection |
| **4 — Admin & Compliance** | 13–16 | RBAC admin portal, PIA-ready documentation, WCAG 2.2 AA audit, load testing, security testing, incident response runbook |

## 3.4 Privacy approach

**Structural privacy enforcement.** PII is architecturally absent from the relay path. Owner's name, phone, email, and location are never loaded into the alert pipeline. The relay engine operates on opaque tokens.

**Privacy architecture designed to support compliance** with the Privacy Act 1988 and Australian Privacy Principles, subject to client legal review. Our scope includes PIA-ready data-flow documentation and technical controls; the final legal and privacy determination remains with client counsel.

**Multi-layered anti-abuse.** Every alert passes a conjunctive gate — rate limits, token validity, owner verification status, plate lookup velocity, sender reputation score. Single failure blocks delivery.

**Full audit trail.** Every data access, moderation action, and system decision produces a cryptographically linked audit record.

---

# 4. Team

| Role | FTE | Responsibility |
|------|-----|---------------|
| **Product / UX Lead** | 0.5 | Product discovery, user journeys, information architecture, interaction design, design system, accessibility, product decisions |
| **Solutions Architect / Tech Lead** | 1.0 | Architecture decisions, privacy review, security sign-off, code review |
| **Senior Backend Engineer ×2** | 2.0 | API, relay engine, anti-abuse pipeline, database |
| **Senior Flutter Engineer** | 1.0 | iOS/Android app, QR scan flow, push handling |
| **Senior Frontend Engineer** | 1.0 | Public web, admin portal, WCAG compliance |
| **T&S / QA Lead** | 1.0 | Test strategy, security testing, abuse case design, moderation workflows |
| **Privacy / Compliance Specialist** | 0.3 | PIA support, data governance, consent architecture, APP alignment |

---

# 5. Delivery Timeline

```
Week  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18
      │───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───│
Phase 1 ████████████████████████████
Phase 2                             ████████████████████████████
Phase 3                                                     ████████████████████████████
Phase 4                                                                     ████████████████████████████
Handover                                                                                                     ████████████
      │               │               │               │               │               │               │       │
    Start        Discovery        Design           Feature        Beta Ready     Prod Launch     Handover  Accept
                 Gate             Gate             Complete                       + Warranty     Complete
```

**Key milestones:**

| Milestone | Week | Gate |
|---|---|---|
| Discovery accepted | 2 | Scope, user research, data flow maps, threat model v1 |
| Design / architecture accepted | 4 | ERD, API contracts, wireframes, infra diagram |
| Feature complete | 12 | All Phase 1–3 features pass internal QA, client demo |
| Beta ready | 14 | Staging live, admin portal functional, UAT |
| Production launch | 16 | Production deployed, monitoring live, smoke tests pass |
| Handover / final acceptance | 18 | Documentation, training, acceptance sign-off |

---


### What we are proposing

| | |
|---|---|
| **Fixed V1 investment** | **AUD $495,000** |
| Delivery period | 16–18 weeks (4 phases) |
| Warranty | 90-day post-launch defect warranty (included) |
| Third-party infrastructure (Year 1) | AUD $77,400 (separate, at cost) |
| Post-launch support | AUD $6,000–$10,000/month (optional) |

> Indicative INR equivalent: ~₹3.38 crore, based on AUD/INR ~68.3 and subject to exchange-rate movement. Final invoicing is in AUD.


# 6. Commercial

## 6.1 Two delivery levels


### Option A — Production V1 (Recommended)

**AUD $495,000**

For a public production launch with genuine trust-and-safety capabilities.

Full scope as described in this proposal: Flutter iOS + Android, responsive web, FastAPI backend, PostgreSQL + pgcrypto, Redis rate limiting, async relay engine, QR discovery with anti-enumeration, multi-perspective abuse detection, structured messaging, RBAC admin portal (4 roles), immutable audit trail, AWS ap-southeast-2, QA + security testing, WCAG 2.2 AA, PIA-ready privacy architecture, production launch + 90-day warranty.

**Timeline:** 20–24 weeks.

### Option B — High Assurance

**AUD $595,000**

For higher regulatory and security requirements.

Everything in Option A, plus:

- Independent penetration testing with formal report and remediation cycle
- Formal security architecture review and threat modelling
- Stronger compliance documentation (full PIA support, APP mapping, regulatory submission support)
- Automated KYC integration (vehicle ownership verification via approved provider)
- More sophisticated anti-abuse intelligence
- Higher availability requirements
- More extensive load testing (10× burst, failover scenarios)
- Production-grade incident response (tabletop exercise, on-call setup)

**Timeline:** 18–20 weeks.

---

## 6.2 Option A — Detailed Financial Breakdown

### How $495,000 is calculated

The underlying delivery value of the RoadSignal V1 product system is $518,300. We are offering a fixed-price engagement at $495,000 — a strategic investment in this partnership.

| Component | AUD |
|---|---:|
| Core delivery (Phases 1–4) | $429,000 |
| Privacy / compliance specialist | $23,200 |
| Delivery risk / contingency (12.5%) | $55,200 |
| Advisory / architecture overhead | $10,900 |
| **Calculated value** | **$518,300** |
| Strategic fixed-price adjustment | **−$23,300** |
| **Fixed V1 investment** | **$495,000** |

### Hours

| Component | Hours |
|---|---:|
| Phase 1 — Foundation | 840 |
| Phase 2 — Relay & Messaging | 880 |
| Phase 3 — Safety & Moderation | 800 |
| Phase 4 — Admin Portal & Compliance | 880 |
| Privacy / compliance (cross-cutting) | 160 |
| **Total delivery hours** | **3,560** |

### Team rates

| Role | AUD/hr |
|---|---:|
| Solution Architect / Tech Lead | $160 |
| Senior Backend Engineer | $125 |
| Senior Flutter Engineer | $125 |
| Senior Frontend Engineer | $115 |
| T&S / QA Lead | $105 |
| Privacy / Compliance Specialist | $145 |
| Product / UX Lead | $130 |

> Rates reflect a premium delivery team with demonstrated experience in regulated platforms, safety-critical systems, and enterprise SaaS. The value proposition is architecture + product thinking + UX + engineering + security + trust & safety — not body-shopping developers.

### Payment milestones

| # | Milestone | % | Amount | Trigger |
|---|---|---|---|---|
| 1 | Contract / Mobilisation | 10% | $49,500 | Signed SOW + NDA |
| 2 | Discovery Accepted | 10% | $49,500 | Client sign-off on discovery pack |
| 3 | Design / Architecture Accepted | 15% | $74,250 | ERD, API contracts, wireframes approved |
| 4 | Feature Complete | 25% | $123,750 | All Phase 1–3 features pass internal QA |
| 5 | Beta Ready | 15% | $74,250 | Staging live, admin portal functional |
| 6 | Production Launch | 15% | $74,250 | Production deployed, monitoring live |
| 7 | Handover / Final Acceptance | 10% | $49,500 | Documentation, training, acceptance sign-off |
| | **Total** | **100%** | **$495,000** | |

Payment terms: 14 days from invoice. Late payment: 2%/month.

---

## 6.3 Third-party infrastructure (separate from project fee)

Volume assumptions: 100K users, 75K vehicles, 500K contact events/month.

| Category | Year 1 Cost |
|---|---:|
| Cloud infrastructure (AWS ap-southeast-2) | $24,600 |
| SMS notifications (Twilio — 900K msgs @ $0.05) | $45,000 |
| Email notifications (SendGrid — 300K msgs @ $0.004) | $1,200 |
| Push notifications (Firebase) | $0 |
| Monitoring (Datadog Pro) | $6,000 |
| Domain, SSL, misc | $600 |
| **Third-Party Total** | **$77,400** |

> Platform provider charges passed through at actuals with no mark-up. These are not our revenue.

---

## 6.4 Post-launch support

### 90-Day Warranty (Included)

- Coverage: Defects in delivered functionality, security vulnerabilities, performance regressions
- Hours: Up to 40 hrs/month
- Response: Critical 4hr, High 8hr, Medium 2 business days

### Essential Managed Support — AUD $6,000/month

- 8×5 Mon–Fri, 08:00–18:00 AEST
- 20 hrs/mo enhancement, monthly security patches, monitoring, incident triage
- SLO: 99.5% uptime

### Growth Managed Support — AUD $10,000/month

- 16×5 Mon–Fri, 06:00–22:00 AEST
- 40 hrs/mo enhancement, bi-weekly releases, dedicated account manager
- SLO: 99.9% uptime

---

## 6.5 Separately priced options

| Option | Cost (AUD) |
|---|---|
| Physical NFC/QR tags (design + tooling + 5K units) | ~$57,500+ |
| Automated KYC provider integration | $20,000 dev + $2.50–4.00/verification |
| Masked voice relay (Twilio) | $15,000 dev + ~$5,400/yr ops |
| Multilingual interface (5 languages) | $45,000 |
| Fleet dashboard | $65,000 |

---

## 6.6 Five-year TCO model

Based on Option A (AUD $495,000 build).

| Category | Year 1 | Year 2 | Year 3 | Year 4 | Year 5 |
|---|---:|---:|---:|---:|---:|
| Build (one-time) | $495,000 | — | — | — | — |
| Cloud hosting | $24,600 | $38,000 | $55,000 | $72,000 | $90,000 |
| SMS (Twilio) | $45,000 | $81,000 | $135,000 | $207,000 | $270,000 |
| Email (SendGrid) | $1,200 | $2,160 | $3,600 | $5,520 | $7,200 |
| Monitoring | $6,000 | $9,000 | $12,000 | $15,000 | $18,000 |
| Domain, SSL, misc | $600 | $600 | $600 | $600 | $600 |
| Software licenses | $3,000 | $3,000 | $5,000 | $5,000 | $5,000 |
| Managed support | — | $72,000 | $120,000 | $120,000 | $144,000 |
| Maintenance & patches | — | $102,000 | $102,000 | $102,000 | $102,000 |
| **Annual Total** | **$575,400** | **$307,760** | **$433,200** | **$527,120** | **$636,800** |
| **Cumulative** | **$575,400** | **$883,160** | **$1,316,360** | **$1,843,480** | **$2,480,280** |

Cost per user drops from $5.75 (Year 1) to $1.06 (Year 5). Cost per contact event drops from $0.10 to $0.02.

---

# 7. Security & Privacy

## 7.1 Security testing

Security testing and remediation are included in all options. **Independent third-party penetration testing fees are excluded from the base project fee** and will be passed through at cost if required. Option C includes independent penetration testing with formal report and remediation cycle.

## 7.2 Privacy architecture

Our scope includes PIA-ready data-flow documentation, encrypted data storage, consent versioning, data access/export workflows, and technical controls designed to support compliance with the Australian Privacy Principles. **The final legal and privacy determination remains with client counsel.**

We do not provide legal advice. We design and build the technical architecture that makes compliance achievable.

---

# 8. Case Studies

## Elevatus (elevatus.io)
Series A. AI-powered Hiring Operating System.** 1.7M+ recruiters globally, 3M+ job fulfillments, 2M+ video interviews, 56B AI matching decisions. Products: EVA-REC, EVA-SSESS, EVA-BOARD. 15+ languages. SAP, Oracle, Zoom, Microsoft Teams, LinkedIn integrations.

**Our role:** Founding product designer (2019) — complete design surface from zero: user research, information architecture, design system, production handoff under startup time pressure.

**Relevant to RoadSignal:**
- Enterprise RBAC and multi-tenant data isolation → admin portal architecture
- Video assessment UX under time pressure with trust → QR contact flow design
- 15+ language platform with RTL → internationalisation architecture
- GDPR-aligned consent management and cascading deletion → privacy architecture
- Anti-fraud detection with human escalation → trust and safety operations
- Rapid MVP to production SaaS → delivery methodology

## Telos CogOS

**Cognitive operating system.** 42 axioms, 9-phase pipeline, 846 automated tests, 31/31 self-audit checks.

**Relevant to RoadSignal:**
- DecisionFirewall (6-check gate) → content moderation gates with audit trail
- CapabilityAuthorization (7-dim conjunctive) → identity verification gates
- DistributedCouncil (5-role advisory) → multi-perspective abuse detection
- HumanGateway (structured verdicts) → escalation workflows

## BitcoinSahi

**Live Bitcoin block-space economics platform.** Real-time data pipeline, admin dashboard, published privacy policy. 17 concurrent endpoints with schema validation.

**Relevant to RoadSignal:**
- Privacy-by-design from day one → encrypted storage, consent architecture
- Validated message pipeline → alert relay with schema validation
- Admin portal with health monitoring → operational dashboards
- WebSocket push and uptime tracking → real-time status and abuse signals

## MealDrama

**Multi-language messaging app.** 8 Indian languages, typed message system, structured templates.

**Relevant to RoadSignal:**
- Typed message system → structured alert reasons (not freeform chat)
- Invite-code join flow → QR discovery pattern (time-limited, one-shot)
- Multi-language framework → i18n architecture from day one
- Role differentiation → reporter vs owner vs moderator data scoping

---

# 9. Assumptions & Exclusions

## Assumptions

- Client provides timely stakeholder access (within 5 business days)
- Client provides domain knowledge for vehicle registration rules and road safety
- AWS ap-southeast-2 deployment (no multi-region V1)
- English-only V1 base build
- No real-time voice/video in V1

## Exclusions

- App Store / Google Play developer account fees
- Marketing, launch campaign, or user acquisition costs
- Ongoing content moderation staffing (tooling delivered; staffing is client responsibility)
- Physical tag manufacturing and logistics (option priced separately)
- Legal review of terms or privacy policy (client's legal counsel)
- Independent third-party penetration test firm fees (engagement scoped; joint selection; passed through at cost)
- State/territory road authority integration or data-sharing agreements

---

# 10. Rate Card- Team

| Role | AUD/hr |
|---|---:|
| Solution Architect / Tech Lead | $160 |
| Senior Backend Engineer | $125 |
| Senior Flutter Engineer | $125 |
| Senior Frontend Engineer | $115 |
| T&S / QA Lead | $105 |
| Privacy / Compliance Specialist | $145 |
| Product / UX Lead | $130 |

---

*End of Document*
