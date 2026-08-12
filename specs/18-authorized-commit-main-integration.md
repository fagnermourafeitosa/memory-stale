# 18 — Local integration after an authorized commit

## Problem Statement

The workflow requires explicit authorization before creating each commit, but it
does not define the next step. This allows an authorized commit to remain only on
its working branch even though the maintainer expects it to be integrated into
the local `main` branch immediately. The result is an incomplete workflow and a
`main` branch that does not represent work that has already been approved.

## Solution

Define that explicit authorization for a commit also authorizes its immediate
integration into the local `main` branch through a fast-forward merge unless the
user says otherwise. Integration does not expand authorization to push, rebase,
create a non-fast-forward merge, tag, open a pull request, or resolve divergence
automatically.

## User Stories

1. As a maintainer, I want an authorized commit integrated into the local `main` branch, so that the approved workflow ends on the primary branch.
2. As a maintainer, I want integration to use fast-forward, so that no unauthorized merge commit is introduced.
3. As a maintainer, I want divergence to stop the workflow, so that rebase or conflict resolution is never inferred.
4. As a user, I want to prevent integration explicitly, so that an exceptional authorization may remain limited to the commit.
5. As a maintainer, I want push to remain a separate operation, so that local integration does not publish changes remotely.
6. As an agent, I want to verify the branch and worktree after integration, so that the reported result is evidence-based.

## Implementation Decisions

- Explicit authorization to create a specific commit also authorizes integrating that commit's dedicated branch into the local `main` branch immediately after creation.
- An explicit instruction not to integrate, to keep the branch isolated, or to follow a different workflow overrides the default rule.
- Before integration, the agent confirms that the commit was created, the worktree is clean, and the working branch contains the authorized commit.
- Integration switches to `main` and accepts only a fast-forward merge.
- If `main` has diverged or fast-forward fails, the agent does not create a merge commit, rebase, or resolve conflicts without new authorization; it reports the blocker and requests direction.
- After integration, the agent remains on `main` and verifies the commit at `HEAD` and the worktree state.
- The working branch is not deleted automatically.
- Authorization does not include push, tag, squash, pull request, or any remote publication.

## Testing Decisions

- Highest observable seam confirmed: Git history and state after an authorized commit on a dedicated branch.
- This is a governance change; no artificial unit test will be created to interpret Markdown instructions.
- Manual validation confirms that a linear case fast-forwards `main`, creates no merge commit, and leaves a clean worktree.
- Contract review confirms that divergent history requires interruption instead of automatic mutation.
- The repository's normal quality gates remain mandatory before the change is considered ready.

## Out of Scope

- Authorizing commits without an explicit user request.
- Pushing or synchronizing the remote `main` branch.
- Creating merge commits, rebasing, resolving conflicts, squashing, or deleting branches.
- Changing the spec-first, dedicated-branch, or TDD workflows.
- Implementing Memory Stale plugin behavior.

## Further Notes

- This spec refines the workflow defined in spec 09.
- “Integrate” in this rule means only advancing the local `main` branch by fast-forward.
