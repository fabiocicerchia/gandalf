---
name: well-architected
description: Review an architecture, change, or IaC against the six AWS Well-Architected pillars — Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, Sustainability — and produce evidence-backed, severity-tagged findings. Use for architecture reviews, design feedback, or when the user mentions "Well-Architected" / "WA review" or asks about best practices for reliability, security, cost, performance, or sustainability.
---

# Well-Architected Review

Apply the AWS Well-Architected Framework when reviewing architectures, writing code, or advising on
design decisions. Evaluate every pillar systematically, cite evidence from the code/IaC, and rank
findings by risk.

> Adapted from the AWS `sample-well-architected-skills-and-steering` steering document
> (github.com/aws-samples/sample-well-architected-skills-and-steering), condensed into a
> self-contained, provider-agnostic rubric. The pillars and principles are general cloud-design
> guidance, not tied to any one platform.

## When to Apply

Apply this skill whenever the user:

- Asks for an architecture review or design feedback
- Requests help designing a new workload or system
- Asks about best practices for reliability, security, cost, performance, or sustainability
- Mentions "Well-Architected" or "WA review"

## Pillars

Always consider all six pillars when evaluating or proposing architectures:

1. **Operational Excellence** — Automate operations, make frequent small reversible changes, refine
   procedures, anticipate failure, learn from operational events. (Observability, deployment risk,
   operational readiness, event/incident management.)
2. **Security** — Implement a strong identity foundation, enable traceability, apply security at all
   layers, automate security best practices, protect data in transit and at rest, keep people away
   from data, prepare for security events. (Identity, permissions, detection, network/compute
   protection, data protection, incident response, application security.)
3. **Reliability** — Automatically recover from failure, test recovery procedures, scale
   horizontally, stop guessing capacity, manage change through automation. (Quotas, network
   topology, distributed-system design, monitoring, scaling, backups, fault isolation, DR.)
4. **Performance Efficiency** — Democratize advanced technologies, go global in minutes, use
   serverless architectures, experiment more often, consider mechanical sympathy. (Resource
   selection, compute, data/storage, networking, caching, the optimization process.)
5. **Cost Optimization** — Implement cloud financial management, adopt a consumption model, measure
   overall efficiency, stop spending on undifferentiated heavy lifting, analyze and attribute
   expenditure. (Usage governance, monitoring, decommissioning, right-sizing, pricing models, data
   transfer, demand management.)
6. **Sustainability** — Understand your impact, establish sustainability goals, maximize
   utilization, anticipate and adopt more efficient offerings, use managed services, reduce
   downstream impact. (Region selection, demand alignment, efficient architecture patterns, data
   management, hardware selection.)

## Design Principles

When proposing solutions:

- Favor managed services over self-managed infrastructure
- Design for failure — assume any component can fail at any time
- Decouple components to reduce blast radius
- Use multiple Availability Zones (or equivalent fault domains) for high availability
- Implement least-privilege access for all identities
- Automate everything that can be automated
- Use infrastructure as code for all environments
- Design for observability from day one

## Review Approach

1. Identify the workload scope and business context.
2. Evaluate each pillar systematically — **do not skip pillars**. If a pillar cannot be assessed
   from the evidence available, mark it N/A with a one-line reason rather than inventing findings.
3. Identify high-risk issues (HRIs) and medium-risk issues (MRIs).
4. Prioritize findings by business impact and effort to remediate.
5. Provide specific, actionable recommendations, citing the file/line and a concrete service or
   pattern to adopt — never "improve security."
6. Reference a relevant Well-Architected lens if the workload fits one (Serverless, SaaS, Data
   Analytics, Machine Learning, IoT, Generative AI, etc.).

## Trade-off Guidance

Acknowledge trade-offs explicitly:

- Security controls may add latency — quantify the impact
- High availability increases cost — present options at different tiers
- Performance optimization may reduce portability — state the lock-in risk
- Cost optimization may reduce resilience — make the risk visible

## Response Format

When delivering guidance:

- Lead with the most critical finding or recommendation
- Group findings by pillar
- Use severity labels: 🔴 High Risk, 🟡 Medium Risk, 🟢 Best Practice
- Include "Why it matters" for each finding
- Provide a concrete next step for each recommendation
