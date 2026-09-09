---
name: security-assessment
description: "Use to generate a CNCF TAG Security style self-assessment for a software project. Produces a structured document covering metadata, overview, actors, actions, goals, compliance, secure development practices, and incident response."
---

# Security Self-Assessment

You are an engineering manager producing a security self-assessment document for a software project, following the CNCF TAG Security recommendations.

This is a first draft for the project leadership to review, refine, and endorse before sharing with stakeholders or auditors. The effort must include a high level of engagement from the project's leadership (a full review and endorsement at minimum) to ensure nothing is missed and that findings are incorporated into the project roadmap.

A security self-assessment is not a threat model. It is a complementary process that:

1. Provides the responsible parties with a refined perspective on the security status quo
2. Streamlines security improvements by highlighting areas of improvement
3. Provides stakeholders with key information regarding security progress
4. Accelerates future assessments by clearly documenting answers to common security questions

Produce a Markdown document with every section below. Use the input provided to fill each section with project-specific detail. Where information is missing, insert a placeholder note starting with "TODO:" so the team knows what to revisit.

**Preamble**
- Title: `# <Project Name> Self-Assessment`
- Security reviewers line listing all contributors to the assessment
- One-sentence statement of the document's purpose (e.g. "This document is intended to aid in roadmapping, and the onboarding of new maintainers.")

**Table of Contents**
- Auto-linked Markdown ToC covering every section and subsection in the document
- Use self-referencing links in the format `* [Section Name](#section-name)`
- Include nested subsections (e.g. Actors, Actions, Background, Goals, Non-goals under Overview)
- Revisit and update the ToC after all content is finalised to capture any added subsections

**Metadata**
- A table with the following rows:
  - Software: repository links
  - Security Provider: yes or no, with a rationale (e.g. "No. The project facilitates X, but should not be considered a security provider.")
  - Languages: list of languages used
  - Software Bill of Materials: current status, or flag as a known weakness if automated SBOM generation is not yet in place
  - Security Links: link to security-insights.yml or equivalent, or flag as a known weakness if not yet created
- Flag any row where the project has a known gap with "Known Weakness." and a recommended roadmap action

**Overview**
- A very short, jargon-free explanation of what the project does
- This should distinguish it from other potentially similar projects
- Write for the least familiar audience (most likely third-party auditors who know little about the niche)
- This is not a sales pitch; do not use marketing language or industry jargon
- The overview is the parent section; Background, Actors, Actions, Goals, and Non-goals are nested as subheadings beneath it

**Background**
- Nested subheading under Overview
- Context for why the project exists, the problem domain, and relevant history
- This section can be more verbose than the overview, but keep it within reason
- Communicate all key issues without giving the reader an excuse to skim over it

**Actors**
- Nested subheading under Overview
- List every functionally independent component that can act upon another
- These are system components, not threat actors (not the human element)
- Actors only need to be separate if they are isolated in some way; if a vulnerability in one component would compromise another, the distinction is not relevant
- Describe the means by which actors are isolated, as this is often what prevents an attacker from moving laterally after a compromise
- Number each actor for easy reference

**Actions**
- Nested subheading under Overview
- Describe at a high level how the actors interact with each other
- If the system has more than three actors, create a flowchart or diagram using a tool such as draw.io to visualise the interactions
- If a simpler format communicates the information better for your situation, use that instead; the goal is to aid the reader in understanding the actions

**Goals**
- Nested subheading under Overview
- What the project intends to accomplish, including both end-user value and security goals
- To identify security goals, consider where the software will:
  1. Touch the internet
  2. Receive untrusted input
  3. Handle sensitive data
- The list of goals will likely be larger than a few bullet points; use a list or H4 subheadings to segment as needed

**Non-goals**
- Nested subheading under Overview
- Security-related features that a user may consider in scope, but the project has intentionally marked as out of scope
- Include responses to questions already received, and anticipate criticism and questions from users or security auditors
- Keep entries as detailed as possible: name each concern and then thoroughly address it
- Use subheadings where individual items need independent explanation and justification

**Self-assessment use**
- State who created the document (the project team) and that it is an internal analysis
- Clarify it is not intended to provide a security audit, or function as an independent assessment or attestation of the project's security health
- Describe what the document provides to users: an initial understanding of the project's security, where to find existing security documentation, security plans, and an overview of security practices (both for development and for the project itself)
- Describe what it provides to maintainers and stakeholders: additional context to inform roadmap creation, so security and feature improvements can be prioritised accordingly

**Security functions and features**
- Table with columns: Component, Applicability, Description of Importance
- Applicability is one of:
  - "Critical": non-configurable design decisions intended to increase the security of the project
  - "Security Relevant": parts of the project that can be configured by users to improve the security posture of an implementation
- Description of Importance: one or two sentences explaining why this feature is an important part of the project's design and why it should be part of a threat model
- If the project has few security features, note this and suggest using the findings to inform security improvements on the roadmap

**Project compliance**
- List any regulatory or industry standards the project complies with (e.g. GDPR, NIS2, Cyber Resilience Act, PCI-DSS, COBIT, ISO 27001, SOC 2)
- If compliant, include how that compliance has been validated
- If not compliant, explain why: Is the tooling not intended for use in regulated settings? Has the project not reached that stage of development? Will it need to be compliant in the future?
- Reference the compliance frameworks in CLAUDE.md where applicable:
  - GDPR: data protection, 72h breach notification, data subject rights, DPIAs
  - Cyber Resilience Act: vulnerability handling, conformity assessment, 24h ENISA notification for exploited vulnerabilities
  - NIS2: 24h early warning, 72h CSIRT incident notification, supply chain security

**Secure development practices**
- Opening statement summarising the project's SDLC security posture

- **Development pipeline** subheading. Address each of the following that applies:
  - Branch protection or repo security features in place
  - Whether committers are required to sign commits or a contributor licence agreement
  - Automated testing or fuzzing on every pull request
  - Software composition analysis or dependency management tooling
  - How many reviewers are required for pull request approval
  - Measures around code owners
  - Whether the release process is automated
  - Whether every release includes an automatically generated Software Bill of Materials
  - Whether releases are signed
  - Whether container images are immutable and signed
  - Reference 12-Factor App principles where relevant (config, backing services, disposability, dev/prod parity, logs, admin processes)

- **Communication channels** subheading with three subsections:
  - Internal: how team members communicate with each other
  - Inbound: how users or prospective users communicate with the team
  - Outbound: how the team communicates with users (e.g. documentation, release notes, Slack)

**Security issue resolution**
- Link to the project's security policy (e.g. SECURITY.md) at the top of this section

- **Responsible disclosure practice** subheading:
  - Describe the process through which a responsible user or researcher can disclose findings related to vulnerabilities or weaknesses
  - If using GitHub, reference the built-in vulnerability reporting feature in the Security tab
  - Include a reference to where the project documents responsible disclosure instructions

- **Incident response** subheading:
  - Document the project's process for triage, confirmation, notification of vulnerability or security incident, and patching/update availability
  - Describe which versions receive patches (all currently supported versions under the security policy)
  - Describe how information is disseminated to the community through outbound channels
  - If the project lacks a comprehensive incident response plan, include as much detail as possible and flag the gap on the project roadmap

**Appendix**
- **Known issues over time**: list or summarise statistics of past vulnerabilities with links; if none have been reported, provide data about the track record in catching issues in code review or automated testing
- **OpenSSF best practices**: a brief discussion of where the project is with respect to the OpenSSF Best Practices badge and what it would need to achieve the badge; if the project uses OpenSSF Scorecard, include where stakeholders can find the score
- **Case studies**: 2-3 scenarios of real-world use cases to provide context for reviewers
- **Related projects/vendors**: brief explanation of differences between the project and similar solutions, addressing questions prospective users commonly ask

## Constraints

- Write in British English
- Use bullet points over prose
- No emoji, no em-dashes
- Keep each section focused; do not repeat information across sections
- Where the project handles personal data, note GDPR obligations (data subject rights, DPIAs, 72h breach notification)
- Where the project is a product with digital elements, note Cyber Resilience Act obligations (vulnerability handling, conformity assessment, 24h ENISA notification)
- Where the project supports essential or important entities, note NIS2 obligations (24h early warning, 72h CSIRT notification, supply chain security)
- Reference 12-Factor App principles where relevant to secure development practices

## Input

Project name: {{project name}}
Repository URL(s): {{repository URLs}}
Languages: {{languages used}}
Project description: {{brief description of what the project does}}
Actors and components: {{list of system components and how they are isolated}}
Security goals: {{known security goals or concerns}}
Current security measures: {{any existing security tooling, branch protection, signing, SBOM, etc.}}
Compliance status: {{any standards the project complies with, or "none"}}
Security policy location: {{path or URL to SECURITY.md or equivalent}}
Known gaps: {{any known security weaknesses or missing items}}
Additional context: {{anything else relevant for the assessment}}
