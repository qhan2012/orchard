---
name: backup
description: "Back up the local site data (targets.yaml, task files, machine memory, reports) to a subfolder of a private GitHub repo that the person gives, or restore missing files from it. Use when the person gives a backup location, says to back up or restore, and after publish, adopt, close, and fallback when a backup location is set."
argument-hint: "[set <clone path or repo URL> <subfolder> | restore]"
---

# Back up the local site data

This repo is public, so the site data is gitignored and has no git history here. The backup puts it in a subfolder of a **private** repo that the person owns.

The location is in `backup.local` (gitignored), one line: `<absolute path of a local clone> <subfolder>`. If the file is absent, there is no backup: say so and stop. Do not choose a location yourself.

## Set the location (`/backup set ...`)

1. The person gives a local clone path, or a repo URL. For a URL: `git clone <url> ~/.orchard-backup/<repo name>` and use that path. If the clone fails (no access), tell the person. Do not try another way to log in.
2. **Check that it is the right repo.** Stop and tell the person if one of these fails:
   - `git -C <clone> remote get-url origin` is not this repo's own origin (never back up into the public orchard repo).
   - The repo is private: `gh repo view <owner>/<repo> --json isPrivate` says `true`. If `gh` cannot tell, ask the person to confirm it once, and write their answer in the worklog.
3. Write `backup.local`. Then run one backup and show the person what went in.

## Back up (`/backup`)

`C` is the clone path and `F` the subfolder. Run from the orchard root:

```bash
git -C C pull -q --ff-only
mkdir -p C/F
tar -cf - --exclude 'tasks/TEMPLATE.md' --exclude '.gitkeep' \
  $(ls -d targets.yaml tasks memory/target-*.md reports 2>/dev/null) | tar -C C/F -xf -
git -C C add F
git -C C commit -q -m "orchard backup <date>"     # "nothing to commit" is fine
git -C C push -q
```

- It copies only the site data. It never removes a file from the backup, so a file that is lost here stays there.
- A new, empty repo has nothing to pull: skip the `pull` then, and push with `git -C C push -q -u origin HEAD`.
- If `pull` or `push` fails for another reason, report the error and stop. Do not force. The copy in `C/F` is still there for the next run.
- Report one line: how many files changed, and the commit.

## Restore (`/backup restore`)

Only when the person asks. It brings back missing files and never overwrites a file that exists here:

```bash
git -C C pull -q --ff-only
tar -C C/F -cf - . | tar -xkf -      # -k keeps existing files; tar then exits non-zero and lists them, which is expected
```

Show the person which files came back. If they want an existing file replaced by the backup copy, they say which one, and you copy that one file.
