trace powered capability indexing

    how can tracing be leveraged to create a numberical index of code such that instructions can be created specific to numerical unique aspects of the code base.  


     design_mode_summary is None in the handoff (B-6)

  The handoff file has design_mode_summary: None and design_mode: None for PI-001. This means:
  - _classify_edit_mode() gets no Tier 2 signal from design_mode
  - The classifier still correctly resolves to mode="edit" (because scaffold has existing_target_files with Tier 1 weight), but with one fewer reinforcing signal
  - More importantly, the upstream DESIGN phase didn't distinguish between "I'm designing changes to an existing file" vs "I'm designing a new feature" — so the design document itself reads like
  a greenfield spec



i am still having issues in the implement phase getting the prompt to update an existing page instead of creating it again from scratch.  look closely at the implement phase prompts to look
  for legacy of the time when the artisan workflow always created artifacts from scratch instead of updating an existing project and it has been very difficult to get the artisan workflow to
  update a page rather than what it has been doing which is creating it from scratch.  Look at the most recent run of the artisan worfklow feature pi-001 for more details.   I've isolate one issue being the design_mode_summary is None in the handoff (B-6)
  The handoff file has design_mode_summary: None and design_mode: None for PI-001. This means:
  - _classify_edit_mode() gets no Tier 2 signal from design_mode
  - The classifier still correctly resolves to mode="edit" (because scaffold has existing_target_files with Tier 1 weight), but with one fewer reinforcing signal
  - More importantly, the upstream DESIGN phase didn't distinguish between "I'm designing changes to an existing file" vs "I'm designing a new feature" — so the design document itself reads like
  a greenfield spec

  
  
  


  i want to focus in on the implement phase and /python-code-refactor how the design prompt happens.  I dont think it was ever optimized after
  /Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/artisan/ARTISAN_PROMPT_EXTERNALIZATION_REQUIREMENTS.md so let's start by ensuring it is well structured to leverage the externalized prompts and there narrow in on ensuring any and all prompt(s) are clear, concise, and complete

    Requirement #2 


i want to add another requirement to this plan /Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/prime/PRIME_EXECUTION_MODES_PLAN.md and requirements
  /Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/prime/PRIME_EXECUTION_MODES_REQUIREMENTS.md  so that second task of this plan is to use the hello world update made in the first requirement to verify successful implementation of /Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/artisan/ARTISAN_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md fully so /Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design-princples/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md can be validated as implemented effectively and programmatically verified via query of the trace(s)