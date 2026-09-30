#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d /tmp/speckit-delivery-install.XXXXXX)"
trap 'rm -rf -- "$test_root"' EXIT
uv run python "$repo_root/scripts/build_release.py" --output "$test_root/dist"
mkdir "$test_root/extension" "$test_root/preset" "$test_root/workflow"
unzip -q "$test_root/dist/delivery-0.1.0.zip" -d "$test_root/extension"
unzip -q "$test_root/dist/delivery-gate-0.1.0.zip" -d "$test_root/preset"
uvx --from specify-cli==1.0.12 specify init "$test_root/project" --non-interactive \
  --integration codex --script py --ignore-agent-tools --extension "$test_root/extension"
unzip -q "$test_root/dist/delivery-workflow-0.1.0.zip" -d "$test_root/workflow"
cd "$test_root/project"
uvx --from specify-cli==1.0.12 specify preset add --dev "$test_root/preset"
uvx --from specify-cli==1.0.12 specify workflow add "$test_root/workflow" --dev
for command in plan demo verify present status gate; do
  test -f ".agents/skills/speckit-delivery-$command/SKILL.md"
done
uv run --script .specify/extensions/delivery/scripts/python/delivery.py --help
if [ -n "${AGENTSTANDARDS_CHECKOUT:-}" ]; then
  python3 "$AGENTSTANDARDS_CHECKOUT/scripts/build_release.py" --output "$test_root/council-dist"
  mkdir "$test_root/council"
  unzip -q "$test_root"/council-dist/agentstandards-[0-9]*.zip -d "$test_root/council"
  uvx --from specify-cli==1.0.12 specify extension add "$test_root/council" --dev
  uvx --from specify-cli==1.0.12 specify preset add --dev "$AGENTSTANDARDS_CHECKOUT/presets/agentstandards-gate"
  test -f .agents/skills/speckit-agentstandards-gate/SKILL.md
  test -f .agents/skills/speckit-delivery-gate/SKILL.md
fi

printf "speckit-delivery-install: PASS\n"
