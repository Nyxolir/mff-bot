# User's farming rules

Locate Daily Task and Special Benefits from their visible captions on each fresh home screenshot. Their vertical slots can shift when shortcuts disappear; never reuse a previous slot. If a mistaken navigation opens the external-link notice, dismiss it with Android Back, then use its verified Cancel control only if Back did not close it. Never accept the link. Check the selected Daily tab before reading daily objectives; Trivia content is not Daily Challenges. Navigation-only unrecognized screens get at most two delayed Android Back attempts before normal bounded recovery. Do not send Back during any submitted battle, Story run or pending/started World Event entry.

Use the Content Status Board as the first daily completion check on every Start Queue and after reset. Inspect its pages in one bounded pass, keep old and current gold-check image variants, and cache verified completions until reset. Reuse board marks for free modes, energy farms, World Event and all four Ultimate Story themes. Do not open completed modes just to check them again. Story is fully done only when all four Ultimate board tiles are checked; a single theme's DAILY REWARD 0/1 blocks starting that theme and requires the board to identify unfinished themes. Mode-specific resource costs, GBR reward clearance, trivia questions and passive Dispatch supplies still need their own verified screens.

After every input, discard any screenshot captured before that input finished. Home navigation must never tap the Settings gear on the game home screen. A verified Settings popup can be dismissed with its OK button without changing options; pending automatic runs stay protected.

Daily Trivia runs between queue tasks once per reset. Read the current question and all four numbered options; choose only a unique matching answer from the local bank. Verify the correct-answer reward popup before closing it, then continue. Preserve the older completed-question list layout too. Unknown questions or unreadable controls stop Trivia without blocking the rest of the queue. Cache completion only after all five answers are verified, and expire it at the normal daily reset.

Stop Queue followed by Start Queue begins a fresh pass through unfinished tasks. Do not trap the new pass on its previous task. Preserve any submitted outcome until two fresh captures positively identify the full undimmed home screen (STORE, TEAM, INVENTORY and ENTER), then hold it for end-of-day review and continue the other tasks. Never infer completion or replay from the old submission. An automatic fight or countdown remains protected until it actually ends; pressing Stop/Start must not cancel it. A generic Home icon is not full home-screen evidence.

Once Timeline Repeat, Otherworld Repeat, Team Arena Repeat or Story Auto Progress is submitted, intermediate results/countdowns are read-only regardless of how long they remain visible. Do not toggle Auto, press Home/Next/Back, swipe, or recover/restart the game between fights. Timeline has the same protection as ticket repeats. A zero-entry transition alone is not proof that the final fight ended. Only a mode-identified terminal repeat notice or the explicit Story Auto Progress Ended summary unlocks result controls. Persist that terminal state across bot restarts. The validated Glory Token capacity confirmation before Timeline begins remains a one-time pre-battle acknowledgement.

After all ordinary daily tasks have drained, revisit enabled unsure outcomes held in the completion cache. Inspect fresh named board counters: mark verified zero/completed entries done; release a verified positive remaining count back to the normal queue, which must reread preparation, full-batch costs and GBR/boost gates. Unreadable or missing counters stay unsure and are revisited after five minutes. Never interrupt a pending battle or protected Story run to review another task, and never infer completion from a generic home icon.

## Prerequisite for boosted farms and Dispatch 7-1

Navigate through Menu > Select Mission > Co-op > Giant Boss Raid.
Select Onslaught and swipe its visible reward strip both ways to inspect both daily remaining counters.
Farming may proceed only when Soul of the Faltine is 0/165 AND Celestial Seed is 0/300.
If either counter is nonzero, unreadable, or unverified for the current daily reset, pause boosted farming and Dispatch 7-1. The user completes Giant Boss Raid manually. Keep the queue running for Timeline, Otherworld, Normal Alliance, World Event and Ultimate Story. Retry incomplete GBR after 60 seconds between tasks; never interrupt a submitted battle.
Never infer completion from entry count, roster availability, or a previous day's check.

Once both counters have been verified at zero in the current daily period, keep that clearance until the next reset. Do not recheck GBR just because ten minutes passed. Daily reset is **15:00 UTC**, equivalent to **17:00 Albanian summer time / 16:00 Albanian winter time**. At the boundary the clearance expires, daily mission completion records reset, and energy farming must inspect GBR again. The app saves verified clearance across restarts until reset; resource balances must still be read fresh before spending.

Last recorded check on 2026-10-18 at 23:27: Soul of the Faltine 63/165; Celestial Seed 121/300. This is a historical observation, not a permanent gate status.

## Other constraints

- Ultimate Story is an explicit energy-only exception to the GBR and boost gate. Open Ultimate, then the ticket icon's Auto Progress tab, require Start from Stage 1-1, and submit once. Let the game advance through the themes with its saved teams, usually about an hour. Never use Normal Story or substitute ordinary repeated pink Start runs. Persist a submitted run to prevent restarting it after a crash.

- Never spend crystals, buy refills, or perform upgrades.
- Sweep tickets and existing energy are permitted for farming, subject to the prerequisite above.
- Wait until enough boost points exist for **every remaining clear in that mission as one batch**. If three entries remain, wait for the boost cost of all three. Never substitute an unboosted clear or a partial batch to use less boost. Read displayed costs and existing energy/ticket balances before committing.
- Start Queue continues through waiting periods and daily resets until Stop Queue. Stop prevents further inputs; an already submitted clear must be verified before another clear can be attempted.
- Use the Content Status Board's mission list, not the Daily Challenges list.
- Leave World Boss and Alliance Battle Extreme/Legend for the user. Normal Alliance Battle may use its built-in auto mode; an existing normal score means it is done.
- Timeline Battle may use auto-run, but Team 1 must be visibly selected first.
- Energy-free farming may run while the Giant Boss Raid prerequisite is incomplete; verify each mode consumes neither energy nor boost points.
- Open automatic Repeat using the gray sweep-ticket icon with blue details. Recognize the icon, not the numeric cost: Otherworld shows -3, other modes may differ.
- When available, select "Play until reward count runs out" rather than running beyond daily rewards. Do not purchase entries or refills.
- Do not assume every board entry is authorized farming; collect remaining rules from the user.
- World Event: use built-in Auto Play+ once per available slot. An existing score skips only that slot. Keep checking closed slots every five minutes, or wait for the observed active slot to end after a scored run. Only a verified daily counter of 0/2 finishes World Event until the 15:00 UTC reset. Persist completion and submitted-entry state across restarts; never retry an uncertain entry in the same slot.

## Port status

The Python 3.12 dependency port, modern OCR/SSIM adapters, rule planner and guarded queue controller are implemented and tested offline.
The current-game screen detector and live UI driver are not yet validated. It is NOT yet a validated unattended current-version farming bot. Do not run the legacy mission queue on the account.


## Requirement-driven additions

Normal Alliance Battle is allowed once per daily reset with the game's built-in auto mode and the existing team. Extreme, Legend and Infinite Challenge are excluded. A completed Normal entry is skipped; the result handler returns home instead of following the Extreme prompt. World Boss remains manual.

Before selecting energy tasks, inspect Daily Challenges and the active entries under Special Benefits. Discover entry names from the current list; exclude Otherworld Battle Pass and Future Pass. The weekly event title is not fixed. Scan each relevant challenge list to its end. Missing progress or an unsupported event layout must not authorize a mission.

Unfinished Dimension clear tasks require one clear in total, even if multiple sources request one. An unfinished Dimension contribution-reward task requires five ticket clears, followed by returning one screen and claiming the bottom-right contribution reward. Completed tasks require no additional clears. With no unfinished Dimension requirement, omit Dimension Missions.

An unfinished event task explicitly requiring a Dispatch clear using energy permits one clear, only on sector 7, mission 1. Use Energy must be checked. Wait for sufficient boost and energy and retain the daily GBR gate. Do not run Dispatch merely for testing when no current event requests it.

Verified GBR clearance is shared by Check Resources, Check Queue and every queued mission. It is saved locally until the next 15:00 UTC reset, including across Stop/Start and app restarts. Only both verified zero counters can create this cache; resource balances are never cached as spending authorization. A session replacement or a newly observed nonzero reward counter invalidates clearance. File Ã¢â€ â€™ Recheck GBR now explicitly discards it and runs a fresh inspection.
# Remembered objectives and passive Dispatch supplies

Dimension and Dispatch requirement checks persist until the next 15:00 UTC daily reset, including zero-required plans. Queue cycles and app restarts reuse this plan. Completing Dimension/Dispatch updates the saved remaining requirement. An in-flight submission invalidates the disk plan so a crash cannot blindly replay a stale objective. The File menu can force a new inspection.

Passive Dispatch supplies use a separate 12-hour clock, independent of daily reset. Save the last verified Claim All time across app restarts; inspect again after 11 hours 50 minutes, then at 10-minute intervals if not yet full. With no saved claim time, use observed supply-bar fill only to schedule the next inspection. A pink notification dot on any verified visible Acquire reward button authorizes Claim All Rewards; sectors share their accumulation clock, so do not pan across the map. Header notifications and supply bars alone never authorize collection. Submit once and verify the reward result/map; never retry an uncertain claim. Perform passive checks between missions, preserving active preparation. Stop Queue stops checking.

Otherworld: check Play until reward count runs out before adjusting quantity. It normally sets all remaining rewards automatically; use MAX if still necessary. Team Battle Arena uses MAX rather than incrementing one by one. Normalize signed displayed ticket deductions before comparing costs. Submit only a verified full remaining batch. Once submitted, leave ticket repeats untouched until an explicit end summary or verified zero remaining count; intermediate results, generic auto labels, menus and unreadable frames must not trigger taps or navigation. If recovery is necessary during an active ticket repeat, stop the bot and leave the game running.

Epic farms open the preparation screen first with the board's Accelerated Clear shortcut off. Read per-clear costs once, open the sweep-ticket popup, then read current balances and submit the full boosted batch. Do not detour into passive Dispatch or World Event checks while preparing a selected mission.


A verified Android launcher is distinct from an unknown game frame. Pause the queue immediately on a fresh launcher observation, save any pending submission, and report that MFF is no longer on screen. A launcher is not evidence of a crash or completed battle. Never restart an active Story/arena run from that observation. Persist Timeline/Otherworld/Team Arena submissions before Start and restore them as verification-only after app restart. A fresh nonzero GBR reward counter is sufficient to keep boosted farming blocked; do not keep scrolling for another counter before allowing free-mode navigation.

Background connection selects the open window by its configured display name and prefers its runtime status ADB port. The bot uses private local ADB server port 5042 so webcam/other ADB clients cannot replace its connection server. Failed connections stop the queue rather than logging indefinitely. An expired restored Arena submission may be reconciled only against fresh named daily-board/lobby counts; a verified home/menu can be used to reach that board. No intermediate battle/result/unknown screen authorizes reconciliation or a second Start. Fresh preparation and costs remain required.

Converging Fates Normal/Hidden are separate energy-only ticket-sweep tasks and run without boost or GBR clearance. Preserve selected difficulty, sweep all remaining daily entries, acknowledge the exact user-approved Crystal Vault full notice, and verify the named claim plus underlying 0/5. Go directly through the chapter Boss/Hidden Boss links between variants; a completed board mark skips only its own variant. Daily Trivia takes priority before board/resource waits at a safe unsubmitted boundary after reset; incomplete checks retry in two minutes.
