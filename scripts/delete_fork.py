import json
import os
import subprocess


def run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] Command failed: {cmd}")
        print(f"[STDERR] {result.stderr.strip()}")
    return result.stdout.strip()


def is_git_repo(path):
    return os.path.isdir(os.path.join(path, ".git"))


def get_codespaces():
    codespaces = json.loads(run_cmd(f"gh codespace list --json displayName,repository,gitStatus"))
    print("Codespaces")
    for cs in codespaces:
        print(f"{cs['displayName']:<25} {cs['repository']:<25} {cs['gitStatus']['ref']}")
    print("-" * 30, end="\n\n")
    return codespaces


def has_uncommitted_changes(repo_path):
    status = run_cmd("git status --porcelain", cwd=repo_path)
    return bool(status)


def has_stash(repo_path):
    stash = run_cmd("git stash list", cwd=repo_path)
    return bool(stash)


def get_unpushed_branches(repo_path):
    branches = run_cmd("git branch -vv", cwd=repo_path).splitlines()
    unpushed = []
    for branch in branches:
        if "[origin/" not in branch or ": gone]" in branch:
            # Check if branch is ahead or has no upstream
            if "ahead" in branch or "[gone]" in branch or "[origin/" not in branch:
                branch_name = branch.strip().split()[0].replace("*", "")
                unpushed.append(branch_name)
    return unpushed


def main():
    # Get list of fork repos you own
    codespace_repos = [x["repository"] for x in get_codespaces()]
    fork_json = json.loads(run_cmd("gh repo list --fork --json nameWithOwner"))
    forks = [x["nameWithOwner"] for x in fork_json]
    forks.sort()
    print(forks)
    deletable = []

    for repo in forks:
        repo_name = repo.split("/")[-1]
        if not os.path.isdir(repo_name):
            print(f"[SKIP] No local repo for fork: {repo}")
            continue
        if not is_git_repo(repo_name):
            print(f"[SKIP] Not a git repo: {repo_name}")
            continue

        dirty = has_uncommitted_changes(repo_name)
        stash = has_stash(repo_name)
        unpushed = get_unpushed_branches(repo_name)

        if not dirty and not stash and not unpushed and repo not in codespace_repos:
            deletable.append(repo)
        else:
            print(f"[KEEP] {repo} (dirty: {dirty}, stash: {stash}, unpushed: {unpushed})")

    print("\nDeletable forks (safe to delete):")
    for d in deletable:
        print(d)


if __name__ == "__main__":
    """Run with python rsb-23/delete_fork.py"""
    main()
