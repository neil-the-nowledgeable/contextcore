# Naming Convention

**Projects as Living Beings in an Ecosystem**

## Philosophy

ContextCore projects are named after animals, reflecting our view that software projects are living systems that interact, adapt, and contribute to a larger ecosystem. Each project has a role to play—observing, connecting, alerting, automating—much like animals in a natural environment.

## Anishinaabe Names

We honor the indigenous peoples of Michigan and the Great Lakes region by including Anishinaabe (Ojibwe) names alongside English animal names. The Anishinaabe peoples have lived in relationship with these lands and waters for millennia, and their language carries deep ecological knowledge.

### Why Anishinaabe?

1. **Michigan Heritage**: ContextCore originates from Michigan, whose name itself comes from the Ojibwe word *mishigami* ("large water" or "great lake")
2. **Ecological Wisdom**: Anishinaabe names often capture the essence of an animal's behavior or role
3. **Restorative Justice**: Using these names is a small act of acknowledgment and respect for indigenous knowledge systems that have been systematically suppressed

## Project Registry

| Project | Animal | Anishinaabe | Pronunciation | Meaning |
|---------|--------|-------------|---------------|---------|
| **ContextCore** | Spider | Asabikeshiinh | ah-sah-bee-kay-SHEENH | "Little net maker" |
| **contextcore-rabbit** | Rabbit | Waabooz | WAH-booz | — |
| **contextcore-fox** | Fox | Waagosh | WAH-gosh | — |
| **contextcore-coyote** | Coyote | Wiisagi-ma'iingan | wee-SAH-gee-MAH-een-gahn | — |
| **contextcore-beaver** | Beaver | Amik | ah-MIK | "Beaver" |
| **contextcore-squirrel** | Squirrel | Ajidamoo | ah-JID-ah-moo | "Red squirrel" |
| **contextcore-owl** | Owl | Gookooko'oo | goo-koo-KOH-oh | "Owl" (internal only) |

### Why These Animals?

**Spider (Asabikeshiinh)** — ContextCore weaves together project artifacts, agent insights, and operational data into a unified observability web. Like a spider's web, it creates connections that capture and reveal patterns across the system.

**Rabbit (Waabooz)** — The rabbit is swift, alert, and always ready to spring into action. Like a rabbit that bolts at the first sign of danger, the Rabbit expansion pack (formerly Hermes) is a trigger mechanism that "wakes up" systems in response to alerts. It receives alert webhooks, parses payloads, and fires actions—then it's done. Rabbit is not a communication channel or workflow manager; it's the alarm that gets things moving.

**Fox (Waagosh)** — The fox is known for its intelligence and adaptability. The Fox expansion pack adds ContextCore integration to Rabbit, enriching alerts with project context for intelligent routing decisions.

**Coyote (Wiisagi-ma'iingan)** — In many indigenous traditions, Coyote is the trickster—clever, resourceful, and a teacher who learns from experience. The Coyote expansion pack (formerly agent-pipeline) automates incident resolution through a multi-agent pipeline, turning tricky production issues into captured knowledge.

**Beaver (Amik)** — The beaver is nature's master builder, known for constructing complex dams and lodges that transform environments. The Beaver expansion pack (formerly startd8) provides LLM provider abstraction—building the infrastructure layer that connects applications to multiple AI providers (OpenAI, Anthropic, local models) with unified interfaces, cost tracking, and token accounting.

**Squirrel (Ajidamoo)** — The squirrel is known for gathering, storing, and retrieving nuts with remarkable memory and efficiency. The Squirrel expansion pack (formerly contextcore-skills) provides a skills library for token-efficient agent discovery—gathering capabilities, protocols, and workflows that agents can retrieve as needed without loading entire context files.

**Owl (Gookooko'oo)** — The owl is renowned for its exceptional vision, watchful nature, and wisdom. In many traditions, the owl sees what others cannot, observing patterns in the darkness. The Owl package (contextcore-owl) provides Grafana plugins for visualization and monitoring—action trigger panels, chat interfaces, and datasources that watch over systems and reveal insights through dashboards. *Note: Owl is an internal sub-component, not a user-facing expansion pack. The name is unofficial and should not be included in user onboarding or the "harbor tour" of capabilities.*

## Cultural Context

### Restorative Justice Mission

The tech industry has historically extracted value from indigenous lands while ignoring or erasing indigenous peoples and their knowledge. By incorporating Anishinaabe names:

- We acknowledge that this software is developed on indigenous lands
- We create small moments of cultural visibility in technical spaces
- We encourage others in tech to learn about the peoples whose lands they occupy
- We model respectful engagement with indigenous languages (not appropriation, but attribution)

### Guidelines for Naming

1. **Research thoroughly**: Use authoritative sources like the Ojibwe People's Dictionary
2. **Include pronunciation**: Help people say names respectfully
3. **Explain meaning**: Share the linguistic and cultural context when available
4. **Keep names stable**: Once assigned, project names should not change casually

### What This Is Not

- This is not a claim to indigenous identity or endorsement
- This is not a substitute for material support of indigenous communities
- This is not comprehensive representation—it's a starting point

## Sources and Attribution

- [Ojibwe People's Dictionary](https://ojibwe.lib.umn.edu) — University of Minnesota, Department of American Indian Studies
- Johnston, Basil. *Ojibway Heritage*. University of Nebraska Press, 1976.
- Nichols, John D. and Earl Nyholm. *A Concise Dictionary of Minnesota Ojibwe*. University of Minnesota Press, 1995.

## Adding New Projects

When creating a new ContextCore expansion pack or related project:

1. Choose an animal that reflects the project's purpose
2. Research the Anishinaabe name using the Ojibwe People's Dictionary
3. Include pronunciation guidance
4. Document the connection between animal characteristics and project function
5. Add to the registry in this document and in [EXPANSION_PACKS.md](EXPANSION_PACKS.md)

---

*"We do not inherit the Earth from our ancestors; we borrow it from our children."*
— Attributed to various indigenous traditions
