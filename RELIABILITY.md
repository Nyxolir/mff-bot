# Why the bot keeps getting stuck

Investigation: 2026-10-24. This is an incident analysis, not a claim that the whole daily queue has completed.

The recurring pattern is brittle screen recognition combined with incomplete testing of transitions. Fixing one screen lets the queue reach another untested screen. The earlier verification that a new fight had started was insufficient: it did not verify the eventual repeat summary, result exit, and next scheduled task.

| Failure | Evidence | Correction |
|---|---|---|
| Dispatch claim controls rejected | Title crop included a help icon; claim-button reference included changing glow | Tightened text/control regions; retained explicit post-claim verification and pending-state protection |
| Epic ticket balance rejected | Dimmed balance OCR split digits with punctuation | Normalized fallback plus exact mission identity checks |
| Arena stopped after temporary capture failures | Four failed screenshots entered recovery, which stopped the protected submitted repeat | Continue polling a fresh submitted repeat; retain the bounded timeout and saved submission |
| Completed Team Arena retained control | Completion saved, then result exit reached home while the old target remained selected | Release a completed task at verified home/menu/board with no pending submission |
| Timeline repeat summary rejected | Old message reference contains an orange mouse cursor. Today's clean screenshot scored 0.9368 against a required 0.96, while OCR read the exact exhausted-entry message | Replace duplicated terminal templates with a shared reader that verifies heading, complete message, mode, and button labels. Blue-text OCR fallback excludes an orange cursor without changing the required wording |
| Timeline result rejected after closing the summary | The reward-title reference includes translucent background. A different character/scenery scored 0.9453 against 0.96; exact OCR still read Timeline Battle Reward | Verify named panel text and contextual labels together with the independently matched Home control. Apply this to Timeline and Otherworld results; retain explicit Team Arena labels |
| A valid completion could be blocked by navigation state | Terminal handler ran after the generic expected-screen wait | Route verified Arena terminal notices before navigation waits, with a matching-pending-mode guard |
| Restart lost its place inside unsubmitted preparation | Otherworld Repeat dialog left the underlying mode title readable, while Menu/Home were unavailable. Board-first navigation waited on that title instead of dismissing the dialog | Reuse bounded Android Back recovery for blocked known Arena lobbies. Verified navigation controls bypass it; any pending submission prevents it |
| Weekly information popup blocked Otherworld | The current weekly character notice covered the lobby during a saved repeat. Existing recognition fell through to the dimmed lobby title, while pending-run protection correctly prevented generic Back | Verify the exact weekly notice heading, explanatory line, mode, and Close label. Authorize only its specific Close; retain the pending repeat and do not infer completion |
| Interrupted repeat retained its original quantity on an idle lobby | After the first Otherworld reward and the weekly notice, the game remained on its full lobby at 4/5 while the saved batch was 5. The bot had no early reconciliation path for this restored, interrupted submission | Require a continuous minute of distinct fresh captures showing the same count, named lobby, usable navigation, and verified ticket control. Then reconcile the saved submission and reread remaining quantity and all ticket costs in preparation. Never reuse the old quantity as Start permission |
| Four-entry preparation kept closing and reopening | Numeric OCR returned blank for the yellow `-9` ticket cost, then generic navigation recovery backed out. The full five-entry cost had previously read successfully | Share Team Arena's yellow-text fallback with Otherworld and retain exact integer/cost validation. Test the actual four-entry form through both the reader and the controller's cost gate |
| GBR full remaining counts were unreadable | Soul `165/165` merged into `1657165`; the Seed crop clipped the first digit of `300/300` and read `007300`. Holding the actual icons independently confirmed 165 and 300 remaining | Cover the complete Seed counter and use white-number normalization, plus independently read yellow cap when necessary. Require a visible slash and correct cap; preserve all zero-counter and missing-text protections |
| Trivia did not reach or finish the daily quiz reliably | Begin-label template mismatch; partially animated answer buttons were treated as a fatal layout error; question 4 OCR became an L; upward scrolling began in a fixed header; question-text OCR changes could bypass duplicate protection | Verify the Start text and control, wait briefly for animations, read the progress number separately, scroll inside the list, and hold pending submissions by question number. Added three game-confirmed answers and verified all five answered rows |
| Weekly Alliance replacement caused navigation recovery | The game showed Relay Boss Battle / Infinite Challenge instead of the Normal/Extreme/Legend selector. The Normal-only reader did not recognize this event and the expected-screen wait rejected it | Verify four independent mode/event labels, accept the weekly screen in Alliance navigation, save a daily skip before exiting, and leave the manual event untouched. Pending submissions and stale evidence cannot authorize a skip |
| Running queue could not be scrolled, and completed entries stayed at the top | Execution disabled the entire QListWidget, which disables its scrollbars too. The status refresh only recolored rows and did not group completions | Keep the view enabled; lock checkbox/drag/edit actions independently. Group current-reset completions below unfinished tasks without rewriting saved priority. Retain scroll and selection, and map sorted rows back to their original entries for checkbox, edit, remove, and duplicate-mode handling |

The Timeline fault does not demonstrate that the previous Arena repair broke Timeline. Its old reader depended on a contaminated reference. The previous checks missed that latent failure.

The input audit records no bot input between Otherworld Start at 19:07:33 and the verified weekly notice Close at 19:12:25. The trigger that interrupted that native repeat is not established. The proven bot defects are its missing notice handler and inability to reconcile the resulting idle lobby promptly; recovery now verifies new state instead of assuming the original batch remains active forever.

The daily board subsequently verified Timeline complete, removed its temporary held status, and retained Team Arena complete. This distinguishes a successful recovery from merely starting another fight. The new result screenshot is also tested directly through the scan/controller/scheduler path.

## Verification required for completion fixes

- Feed actual captured screenshots through `ScanTask`, then the queue's evidence/controller path.
- Verify the terminal state is saved before sending its acknowledgement.
- Verify the underlying result or a fresh zero-entry board, then release the active task and let the scheduler select another task.
- Preserve no-input behavior for intermediate fights, another mode's summary, stale observations, and failed state saves.
- Keep both cursor-bearing desktop captures and clean ADB captures in the regression set. Do not lower global visual-match thresholds to make one screenshot pass.
- Keep existing Dispatch, Story, reward, daily-reset, capture, and mission checks in the full regression run.

Implementation remains in `2026-10-18/https-line-tivi-ott-net-get/outputs/mff-auto-modern`. Current live outcome and validation counts are recorded in BOT-STATUS.md after verification.

## Verified outcome

All 397 regression tests passed in 122.566 seconds after the final reader change. The live Otherworld run then reached its explicit end notice at 19:27:28, named result at 19:27:33, verified home at 19:27:39, and lobby with 0/5 remaining at 19:28:02. Its saved pending submission was cleared, all three Arena modes are cached complete, and no Arena outcome remains held. This validates the terminal path in the running game as well as the fixtures. It does not establish that every other daily mission has completed.

After the GBR counter repair, all 400 tests passed in 126.039 seconds. Both hold tooltips corroborated the actual nonzero counts. The deployed reader recognized Seed 300/300 and Soul 165/165, and the resource controller exited with an explicit rewards-remain message rather than an unreadable-counter swipe loop. The raid gate correctly remains closed.

The live Trivia quiz subsequently finished 5/5 correct. Its completed list was verified and cached with five verified questions and next-reset expiry. Daily queue tests cover same-day restart skip, incomplete retry, preservation of a completed day after a failed optional recheck, and an automatic attempt at the next reset. Details are in TRIVIA-STATUS.md.

The Alliance repair passed all 415 tests in 183.291 seconds before the subsequent queue UI change. Its weekly skip was verified live and restored after restart. Native desktop checks then verified mouse-wheel scrolling both directions while the queue was running and completed tasks grouped at the bottom; the queue was returned to its previous stopped state. Final combined validation is recorded in BOT-STATUS.md.

Final combined regression run: all 421 tests passed in 192.746 seconds. The updated desktop is open and connected, left stopped after the live scroll check. Trivia and Alliance daily state remain saved; no submission is pending.

## Zombie Survival integration

Added the weekly mode without hardcoding roster identities. The controller verifies Level 1, empties previous selections, scrolls to the roster top, selects the first five positions with slot confirmation after each tap, opens ticket repeat, verifies MAX and its exact ticket cost, and persists the batch before Start. The live maximum was five runs for twelve sweep tickets, with a free first run.

The observed terminal flow differs from Arena: a NOTICE says Auto-Repeat has ended and shows 5/5 Survived over Survival Success. The result Home icon, Challenge Reward receipt, dimmed COMPLETE challenge rows, and scrolled gold completion tile all have actual screenshot regressions. These controls were added while retaining the saved submission; no duplicate Zombie Start was issued. Running timeouts and post-run collection waits are separate so an old running deadline does not prevent acknowledgement or collection after a verified end.

Acquire All was verified live after the fifth-clear challenge reached 5/5. The receipt awarded 460 Zombie Survival Tokens, 20 crystals, and 1,000 Eternal Flame, and the weekly Challenges wheel showed COMPLETE. The explicit board tile was verified complete at 23:54:31 Europe/Budapest on October 24; pending state is empty. Completion is rechecked against the board after daily cache expiry, preserving the game's weekly state instead of assuming a weekly reset date.

The earlier whole-list editing lock and completed-item sorting fixes remain in place. Final combined test results and current deployment state are recorded in BOT-STATUS.md.

Final Zombie integration validation: all 449 tests passed in 209.949 seconds. The desktop was resumed and restored Zombie completion. Native inspection confirmed its enabled row reads Done · weekly rewards verified at the bottom of the running queue, and scrolling still works. The input audit contains exactly one Zombie Start; pending state remains empty.

## World Event cached board completion

The previous board preflight applied its normal completed-tile and unfinished-prefix rules to World Event. Its board can retain a cached 0/2 until the event page opens, so those shortcuts could mark the day done without a run. The saved record had done=true and before=null; the current event page showed 2/2 and Best Score 0. The problem was trusting cached board completion, not an unreadable event counter.

Removed both board-to-done paths for World Event. Only three fresh 0/2 observations from distinct reopened event-page visits can produce a durable daily completion. They must be spaced at least three seconds apart; same-visit or duplicated captures do not advance the check. Positive entries discard the zero candidate. Cache version 2 stores this proof and rejects older unverified done flags while preserving pending and started latches. A submitted battle never navigates away or clears its latch merely because a zero lobby frame appears.

The repaired live controller entered from the verified 2/2 page, completed one Auto Play run, acknowledged End Battle, and reopened the page to verify 1/2 and Best Score 3,452,508. The durable cache remains done=false with pending=false and started=false. All 462 tests passed in 223.051 seconds. The desktop queue resumed at 00:20 and shows World Event unfinished. Detailed evidence and deployment state are recorded in WORLD-EVENT-STATUS.md and BOT-STATUS.md.


## Dimension requirement freshness and spending priority

A same-day objective cache recorded five clears plus contribution. At 01:27 Europe/Budapest the GBR gate was verified clear, but the scheduler used the saved energy mission order and spent on Beginning of the Chaos and Cutting Cable before Dimension. A forced inspection independently found Event Quest Clear 10 Stages, 0/10, and calculated ten clears plus contribution. This was a cache freshness and scheduling defect, not a failure to parse that ten-clear screen.

Queue starts now require a fresh objective inspection before new boosted farming. Required enabled Dimension Mission takes priority after GBR. Other boosted missions remain blocked while its full batch waits for resources or reconciliation; pending submissions are never preempted or retried. Live outcome and final suite results are maintained in DIMENSION-STATUS.md and BOT-STATUS.md.

The live Dimension sweep then failed only its ticket-icon match (0.9425 versus the required 0.96); energy and boost-notice anchors were valid. A static icon crop from the observed ADB 1080p screen now supplements the retained older reference. No global threshold was reduced. The current popup verifies 8 energy, 2 tickets, and 4 boost per clear, and negative tests still reject missing icons or boost notice. Final validation and terminal verification are in DIMENSION-STATUS.md.


Dimension terminal verification completed at 02:01:33 Europe/Budapest on October 25. One ten-clear Start consumed 80 energy, 20 tickets and 40 boost. The result showed ten clears and 120/60 contribution. The old generic counter rejected surplus progress, and the old collector only opened the reward list. Added explicit list, Acquire All and Acquired-receipt handling with durable latches and post-claim counter verification. The receipt awarded 4,000,000 gold and 6,500 Support Tokens; contribution then showed 0/60. Completed state is persisted and both pending and held are empty. Cutting Cable was separately reconciled from its explicit completed board tile, without replay.

Also retained the older dark-number OCR fallback while adding the current padded number treatment for multi-digit energy costs. Dimension result routing now verifies its clipped mode title, centered Close and contribution bar before Epic routing. Menu overlays are recognized before the underlying board during claim recovery. The objective plan and collection latches survive restart. Full final suite results and deployment status are maintained in DIMENSION-STATUS.md and BOT-STATUS.md.

Final Dimension integration validation: all 484 tests passed in 238.360 seconds. The desktop resumed at 02:06 and restored Dimension completion and GBR clearance. Native inspection confirmed Stop Queue and the requirement-check waiting state for other boosted rows. Pending and held are empty.


## Recurring exact ticket-stock OCR; user switches to boost-only checks

The October 25 recurrence was caused by both ticket-stock OCR crops returning 1,249,01 and the strict number parser rejecting it. Previous crop widening fixed one rendering but retained the unnecessary requirement for a complete inventory number. The bot repeatedly deferred Rise of the Phoenix, Shock and Awe and Sinister Schemes without submitting them.

The user explicitly requested boost-only resource checks for every content mode. Removed energy and ticket-amount OCR/validation from active sweep, Dispatch, Story and repeat paths. Boost affordability for full boosted batches, GBR clearance, mode and quantity proof, zero-crystal policy and pending latches remain. No guessed inventory number or synthetic balance is substituted.

Live verification completed Sinister Schemes as a two-clear batch and verified its exact result and exit. Pending and held are empty. New blank-resource and failing-screen regressions are retained. Final suite/deployment details are maintained in BOOST-ONLY-STATUS.md and BOT-STATUS.md.

Final boost-only validation: all 490 tests passed in 234.964 seconds. The desktop queue restarted with its existing saved completions. Sinister Schemes was verified complete live, and pending and held were empty at exit.


## 25 October: Converging Fates and early Daily Trivia

Added separate [NORMAL] and [HIDDEN] Converging Fates tasks. Both use the observed
Multiverse Saga difficulty/Ready/Sweep/Claim All flow and the whole remaining
batch with tickets. No energy, ticket-stock or boost-stock OCR is used; the two
explicit zero-boost modes bypass GBR and Dimension boost priority. Other farming
keeps its existing boost/GBR policy. Exact stage/reward identity separates the
variants; opaque sweep popups require a fresh matching Ready capture. Pending
submission persists before input, reward acknowledgement keeps it pending, and
underlying verified 0/5 completes it. Restart, mismatched result, missing/stale
preparation and persistence failure checks prevent repeats. The user approved
the exact full Crystal Vault notice. Normal-to-hidden navigation uses the chapter
links directly, and independently completed board tiles skip only that variant.

Live manual ticket sweeps completed five normal and five hidden entries; both
Ready screens showed 0/5 afterward. Full automated spending uses regression
fixtures captured from this live flow; no extra entries were spent for testing.
The earlier trivia session stopped on a genuinely missing Elektra question.
Added Elektra and Mockery, then the bot answered them correctly, continued to
Baxter Building/Fear and verified all five completed rows. Completion is saved
for the current reset. Verified answer additions now reload from
settings/gui/trivia-answers.json for each question without restarting the GUI.

The scheduling cause was the old trivia check's requirement for queue_target to
be empty, its placement after board preflight, a 15-minute retry, and retry delay
that could carry across reset. Trivia now runs at a safe unsubmitted boundary
before board/GBR/boost waits, retries after two minutes, and resets that delay at
15:00 UTC. Submitted battles, Story protection and recovery remain guarded.

Validation: full suite 505/505 passed (288.046 seconds); 11 targeted Converging tests plus navigation and one-entry/full-flow checks passed after final edits. The newly deployed live queue independently remembered both variants as complete from the board and continued the queue. Trivia completion remains 5/5 in its daily cache. Evidence and source hashes: diagnostics/converging-trivia-oct25-validation.json.

Validation: full suite 505/505 passed (288.046 seconds); 11 targeted Converging tests plus queue-entry navigation and one-entry/full-ticket-flow checks passed after final edits. The deployed live queue independently remembered both variants as complete and continued World Event. Trivia remains 5/5 in its daily cache. Evidence and source hashes: diagnostics/converging-trivia-oct25-validation.json.


## 25 October evening: Dimension gold receipt and lost claim recovery

The 22:37 inspection planned five clears plus contribution. One full five-clear batch was submitted at 22:38:05; the named result verified five clears and 60/60 at 22:38:21. Acquire All was issued once at 22:38:34. The taller Acquired popup says 4,000,000 Gold acquired! and shows the underlying counter at 0/60. The item-receipt body crop ended above this gold text, and its OK coordinate was above this layout's button. The reader returned unknown. Generic recovery then held Dimension, discarded its pending claim snapshot, restarted the game and searched an unsuitable content-board path.

Added a distinct gold-receipt layout requiring Dimension title, Acquired heading, exact gold-acquired body and OK identity. The older item receipt and global thresholds remain. Acknowledgment retains pending until the contribution counter drops. Generic recovery and restart now stop with the confirmed Dimension batch and objective/claim latches saved. Legacy holds are reconciled only after a complete fresh objective inspection, with no submitted batch pending. Completed contribution plus zero remaining clears marks it complete; a positive remaining objective releases only that remaining batch to normal boost/GBR preparation. A still-required contribution claim or failed state save keeps it held.

Live reinspection at 23:01 found contribution 1/1, but Event Quest still at 5/10. Its half-filled cyan bar caused the old raw color-number crop to lose 5/; the reader failed rather than authorize spending. White-digit isolation now reads 5/10, while retaining the old treatment as a fallback and rejecting missing progress. Regression fixtures also verify the older 0/10 and completed 10/10 pages. The earlier 22:35:52 home capture missed the Event Quest shortcut, so that inspection skipped the event and planned only the five clears implied by contribution. Absence now needs three home reads at least three seconds apart; if the shortcut appears, the event is inspected using its current observed position.

Preserved actual screenshots: dimension_gold_receipt_oct25.png, dimension_event_quest_partial_oct25.png, dimension_five_sweep_oct25.png and dimension_five_sweep_result_oct25.png under tests/fixtures. Thirteen focused claim/recovery regressions include ScanTask through acknowledgment, counter-drop completion and next-task scheduling; stale/mismatched evidence; state persistence and restart; legacy hold reconciliation through 5/10, an exact five-clear batch and its result; and failed save rollback. Objective tests additionally cover transient and genuine shortcut absence. Final suite and live state are recorded in diagnostics/dimension-gold-recovery-oct25-validation.json.

Final verification: all 523 regression tests passed in 276.319 seconds. Deployed at 23:13 CET. The live inspection read Event Quest 5/10 and contribution 1/1, finished all eligible event pages, and derived exactly five remaining clears with no contribution claim at 23:15:40. It removed the legacy hold, kept Dimension ahead of other boosted farming, submitted one five-clear/20-boost batch at 23:16:32, verified its named five-clear result at 23:16:49 and selected Beginning of the Chaos at 23:16:52. Dimension is saved complete; pending and held were empty at its exit. The old gold popup was validated through its saved fixture, not claimed as a second live receipt acknowledgment.


## 26 October: recover a fully exited BlueStacks player

The old capture path retried the cached emulator-5554 device after the player disappeared. Logs from 23:48-23:49 repeat device-not-found every six seconds. Game recovery only uses ADB to relaunch MFF inside an existing player, so it cannot revive a closed emulator. The user requested automatic player relaunch.

The new worker checks a readable Windows process snapshot before launching. When no HD-Player exists it starts the remembered configured instance through the installed HD-Player.exe --instance argument. The local desktop shortcuts independently confirm Pie64 and this exact syntax. If a player is already running, recovery reconnects only when the selected instance's exact window is present; it never launches a duplicate or attaches an old port to an unidentified player. Boot/reconnection is bounded to 150 seconds and two recovery attempts per hour. Stop Queue cancels subsequent actions. The verified installed MFF package is opened without force-stop or resending prior game input.

Before recovery, pending submissions are saved and game input is disabled. The worker preserves daily completion, contribution latches, protected repeat state and Dispatch/World Event scheduling. After connection it drops stale observations and preparation, requires fresh objectives, and waits for game loading. An unverified interrupted submission reaching actual game home stops with pending intact; a verified result or already-confirmed contribution/repeat end can continue through its existing reconciliation.

Focused tests cover vanished player, temporary ADB loss, another running instance, cancelled/failed boot, invalid identity/disabled ADB, exact package/instance launch, save failure, rate limit, stale frames, pending home, real Dimension receipt/result fixtures and subsequent scheduling. Read-only live recovery reconnected Pie64 at native emulator-5554 and 1920x1080, returned a fresh frame and launched neither emulator nor game. A live crash was not deliberately induced. Final full-suite results and deployment evidence are in diagnostics/bluestacks-recovery/validation.json.

Final emulator recovery validation: 549/549 tests passed in 350.512 seconds; 47 focused tests passed in 5.294 seconds. The updated GUI was deployed at approximately 00:08 CET on October 26, reconnected to the existing selected emulator, restored saved completions and resumed the queue. Native inspection verified Stop Queue; the bot completed board preflight and began fresh objective inspection at 00:09:02. No submission was pending during deployment and all saved completions were retained. Full closed-player startup remains validated through simulated tests; the live read-only reconnect path was exercised successfully.


## 26 October evening: capture failures, targeted restart and Converging ADB OCR

The actual incomplete-capture exception ended in "reconnect". Substring transport classification burned both hourly reconnect slots on malformed frames, stopping the queue with a five-run Arena batch saved. Capture failures now retry for a continuous minute without consuming recovery attempts; fresh captures reset that clock. Persistent bridge failure permits one stop of the verified selected HD-Player PID and its process tree, private ADB server 5042 reset, and relaunch of remembered Pie64. Stop Queue cancels recovery. Saved submissions remain protected and unknown interrupted outcomes are never replayed.

Live Arena result recognition already worked: 2 wins plus 3 defeats verified all five runs, cleared pending, saved Arena complete and advanced to World Event. World Event completed its remaining entry and verified 0/2 on three reopened pages at 22:04:57, 22:05:09 and 22:05:21 UTC. No Arena run was repeated.

The subsequent Converging screen exposed independent OCR faults: generic heading OCR missed NOTICE on an ADB frame and yellow-number preprocessing misread the visible 5/5 as 3/5. White heading OCR plus the exact approved Crystal Vault body and OK control recognizes this notice; standard text OCR reads the whole counter. Actual screenshots are retained as converging_vault_adb_oct26.png and converging_ready_adb_oct26.png. ScanTask/controller regressions cover approval, exact five-ticket submission, named claim, zero-entry completion and direct Hidden routing, alongside previous fixtures and negative controls.

Final suite: 561 tests passed in 300.626 seconds. With queue stopped and pending empty, the authorized live restart stopped only the selected player, relaunched Pie64, reconnected and opened MFF; a later screenshot showed the actual login screen. Saved Arena/World Event completion remained intact. Updated GUI deployed connected with queue paused. Automatic approval review rejected --start-queue because resource spending required explicit approval; approval was requested asynchronously. Converging terminal flow is fixture-verified, not yet live-verified. Evidence and hashes: diagnostics/restart-repair-oct26/validation.json.

The user subsequently explicitly approved resuming the existing daily queue. Start Queue was invoked on the deployed connected GUI at approximately 23:31 CET, without changing saved targets/settings. Live verification continues below.

Live follow-through recognized the native Vault notice but exposed the same generic-blue-heading OCR loss on Sweep. Added the exact native Sweep fixture to the complete ScanTask/controller flow and independent negative prompt/label/batch-control cases. Sweep now uses the same white-heading fallback, while cropping the ticket identity label before its cost amount. Final suite: 562/562 passed in 367.306 seconds. Deployed and resumed the user-approved existing queue after the safe unsubmitted pause; live terminal verification follows.

Final reader live proof: Normal submitted five sweeps at 23:45:03, waited for the named five-clear result (an earlier animated result read only two), acknowledged it, then verified 0/5 and saved completion at 23:45:22 CET. Hidden completed its own five sweeps and 0/5 at 23:47:54 CET. Both are saved complete with no repeat. The queue then checked GBR and launched the existing configured Ultimate Story Auto Progress at 23:49:45, preserving its dedicated story-run.json latch.

Live checking exposed a separate trivia navigation problem: ObjectiveReader verified Menu/Home on unrelated mission pages but returned unknown; TriviaSession deliberately waits on unknown frames, so it never reached the navigation fallback. TriviaReader now emits explicit navigation-only evidence from those verified controls. Unknown question/result layouts still cannot authorize an answer. The scheduler now retries trivia between tasks or during a real resource wait, retaining early-reset priority while leaving active Converging preparation/direct chapter handoff intact. Six targeted tests include the actual ADB mission frame, stale evidence and pending-answer protection, startup priority and boost-wait preemption. Full-suite verification is pending while the existing Story run continues.

Live recovery recurrence: at 23:59:18 CET the exact incomplete-screenshot/reconnect exception recurred during protected Story. The new capture-only retry path retained the active run, reconnected at 23:59:34, and verified Story Auto and Progress on at 23:59:37. No emulator restart, new Story launch or hourly recovery-budget exhaustion occurred. Final full-suite testing for the additional trivia navigation/boundary changes continues under low physical-memory availability; port development is paused at the user's explicit priority instruction.

Final follow-up suite: 565 tests passed in 621.058 seconds under host memory pressure. Gracefully paused only the bot interface, saved the active Story tuple and existing original start timestamp, closed the GUI and relaunched it minimized with the explicitly approved queue. BlueStacks/game were left running. Trivia fixes are deployed; live quiz completion must wait for the protected Story run to finish.

Post-deployment verification at 00:04 CET October 27: the minimized GUI restored both the dedicated active Story latch and pending STORY ULTIMATE tuple. It reconnected, resumed queue verification and observed the same battle. The input audit remained unchanged at the original 23:49:45 launch; no new Story or other game input was sent during the interface replacement. A retained battle screenshot shows Auto Progress and Auto Play checked on stage 3-1. The actual daily quiz remains incomplete and cannot be claimed cleared while Story is protected.

## October 27: completed trivia, notification drawer and network retry

The earlier trivia navigation follow-up passed 567 tests. Actual quiz inspection then found a quest drawer covering the option buttons and two absent answers: Moon Knight and Muspelheim. Added both to the persistent, hot-reloaded answer file, checked their official Marvel references and retained the game's correct-result receipts. The other three answers were already supported. The bot verified all five answered rows and saved daily completion at 03:21:52 UTC, expiring at 15:00 UTC. Evidence is in diagnostics/trivia-oct27/.

Drawer recovery runs before specialized readers and taps the exclamation circle only after identifying the cyan footer, upward arrow and first quest heading/objective. The footer height varies with the number of rows; actual one-row and four-row fixtures are retained. Live deployment at 03:29:10 UTC closed the one-row drawer, reread the page, verified the board's completed section and continued to GBR. No quiz was repeated after restart.

A real network notice interrupted one answer request. The user instructed OK; the game later reloaded and the quiz continued. Shared recovery now recognizes NOTICE plus the exact connection/retry message and both Cancel/OK controls, ignoring the variable NET error number. It preserves pending answers and submissions, requests fresh evidence, and bounds acknowledgements to three in five minutes with at least 20 seconds between attempts. Original fixture/controller checks cover changed/missing error codes, masked controls, stale/saved/idle observations, preserved pending state and retry exhaustion. This automated network path has not been induced live. A full 578-test suite passed in 497.175 seconds; the subsequent 579-test drawer-variant run was interrupted at the user's stop request.

## October 27: ignore challenges from a verified max-level pass

The Emblem Upgrade Special Pass showed MAX LEVEL, while its completed daily rows still showed Acquire. The old inspection kept scrolling because no COMPLETE tail was visible and small OCR variations prevented repeated text signatures from matching. This was separate from boost waiting. The old queue eventually escaped the OCR loop, derived the Event Quest requirement of ten Dimension clears, completed that batch at 03:40:33 UTC and correctly waited for boost on later Epic content.

The reader now requires the pass header/title, explicit MAX LEVEL text and both ends of its full cyan progress bar. The inspection matches this title to the selected benefit, discards requirements only from that pass, records the skip and proceeds to the next source. It does not assume a numeric cap or waive Daily Challenges/Event Quest. Current maxed-pass and non-maxed Weekly Elite Gear screenshots are saved; tests also cover a weekly layout with verified max evidence, masked identity/bar/text, mismatched event names and retaining the ten-clear plan through ScanTask/controller processing. Fifteen focused inspection tests and the queue transition test passed. The full suite is running; the updated interface was safely deployed at an unsubmitted boost wait and resumed the existing queue. Live max-level skip verification follows.

Live proof after deployment: ObjectiveReader identified the Emblem pass as verified MAX LEVEL, the inspection left its challenges immediately, completed its remaining-source checks and saved a zero remaining Dimension requirement (the earlier ten clears were already confirmed). The queue resumed CUTTING CABLE and correctly waited for 12 boost with 7 available. It did not repeat Dimension clears or trivia. Actual max-level evidence and resumed-queue log are retained in diagnostics/trivia-oct27/max-level-*.

Final verification: 585 tests passed in 433.338 seconds. The first run's sole error was an older emulator-recovery test mock missing the new max_level_passes diagnostic field; its fixture was updated, its focused test passed and the entire suite then passed. No additional production change or redeployment was needed for that test-fixture correction. Current source/log hashes and daily trivia proof are saved in diagnostics/trivia-oct27/validation.json. The resumed queue subsequently confirmed CUTTING CABLE and advanced to ENDING THE STRYFE; waiting for its full-batch boost is intentional.


## October 28 Daily Trivia additions

The stopped queue had repeatedly encountered the unknown Sacred Timeline question. Added TVA and the later missing condensed-artifact-material answer Celestial Essence to the existing hot-reloaded answer file. The bot submitted both and received verified correct receipts; the other three answers were already supported and also correct. The bot then read all five answered rows and persisted daily completion through the October 28 15:00 UTC reset. No reader/controller changes or mission-state resets. Existing queue remains stopped as found. Trivia suite: 26 tests passed. Evidence: diagnostics/trivia-oct28/validation.json and bot-trivia-run.log.


## October 28: finish trivia from its completed summary

The user confirmed that the Daily Trivia question-and-answer list only appears after the quiz is complete. Removed the session's top/bottom scrolling and five-row collection requirement. The reader verifies the Challenges / Daily Trivia summary, row geometry, a tightly cropped ANSWER label and displayed answer, and gold answers on the visible rows. Short-answer OCR misses elsewhere do not force scrolling. Unknown, unfinished and unverified screens still cannot mark completion.

The reloaded idle bot was checked live at 00:34:19 Europe/Budapest: its first summary scan immediately finished trivia and saved completion through the October 28 15:00 UTC reset. Input audit contained no new game taps or scrolls. Pending submissions, completed missions, Story, World Event, Dispatch, objectives, GBR and answer-bank fingerprints all stayed unchanged. The queue remains stopped as found. Evidence: diagnostics/trivia-summary-oct28/live-validation.json. Five historical/current summary screenshots also completed with zero session inputs; the full regression suite passed: 587 tests in 662.473 seconds (diagnostics/trivia-summary-oct28-suite.log).

## October 28 after reset: Olympus and Silver Samurai trivia answers

The bot stopped on question 2 (the character who is not a god of Olympus) and question 5 (Silver Samurai's sword) because those exact questions were absent from the local answer bank. Added Loki and Muramasa Blade to the existing hot-reloaded trivia additions. Both submissions received the game's explicit correct-answer receipts. Questions 3 and 4 were already supported and also received correct receipts; question 1 had already been answered before this run.

The bot then verified the completed question-and-answer summary and saved daily completion for the October 28 15:00 UTC period, expiring October 29 at 15:00 UTC. It did not scroll to expose or count every summary row. Ten game inputs covered navigation, answers and receipt acknowledgements; zero scroll inputs were sent. The main queue remains stopped as found. A temporary quest overlay delayed the first layout read but cleared on reinspection; no reader/controller changes were needed.

Validation: all 29 focused trivia tests passed in 31.017 seconds. New cases exercise both observed questions through OCR, named option selection and pending-answer protection; the new completed summary also passes the zero-input completion regression. Local screenshot fixtures, account state, input audit and detailed validation remain excluded from Git. Evidence: diagnostics/trivia-after-reset-oct28-validation.json and diagnostics/trivia-after-reset-oct28-suite.log.

Standing publication rule added to AGENTS.md: verified bot/answer changes must be committed and pushed to Nyxolir/mff-bot, using Nyxolir's no-reply author identity and preserving private runtime exclusions.

## October 28: Windows installer and automated releases

Replaced the obsolete Python 3.6 build downloader with a pinned Windows x64 application bundle and per-user Inno Setup installer. Python, Node/Tesseract.js and the existing English model are included. Immutable templates and default answers stay with the application; installed settings, pending outcomes, completion caches, custom answers and diagnostics live under `%LOCALAPPDATA%/Nyxolir/MFFBot`. Source runs retain their existing paths. Default answer updates merge with user additions while retaining the known-answer conflict guard.

The full regression suite passed all 592 tests in 326.516 seconds after the shared path/OCR changes. The frozen GUI and offline OCR self-test passed, including both private Olympus/Silver Samurai screenshots. The installed application passed the same offline check. Reinstall preserved synthetic pending-state and custom-answer files byte for byte; uninstall removed the program while preserving those files. No game connection or queue was started. Installer notices use short filenames with their original paths recorded in the dependency inventory, avoiding the Windows path-length failure found by installation testing.

Bundle contents, embedded Python source filenames, the compiled installer and tracked source passed the personal-identity audit. Private screenshots, runtime settings and diagnostics are excluded. Local evidence: `diagnostics/installer-full-suite.log`, `build/installer-c_66a7dz/application-selftest.json` and `build/installer-c_66a7dz/installed-smoke-final/installer-validation.json`. The GitHub workflow independently rebuilds and verifies installation before publishing a versioned release with source, manifest and checksums. A failed build preserves the previous successful release.
