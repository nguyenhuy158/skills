#!/usr/bin/env bash

set -Eeuo pipefail

protected_image="farmnet:local"
dry_run=false
confirmed_plan=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            dry_run=true
            shift
            ;;
        --keep-image)
            protected_image="${2:?Missing image after --keep-image}"
            shift 2
            ;;
        --confirm-plan)
            confirmed_plan="${2:?Missing plan ID after --confirm-plan}"
            shift 2
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            exit 2
            ;;
    esac
done

docker info >/dev/null
docker image inspect "$protected_image" >/dev/null

if [[ "$dry_run" == true && -n "$confirmed_plan" ]]; then
    printf 'Use either --dry-run or --confirm-plan, not both.\n' >&2
    exit 2
fi

if [[ "$dry_run" != true && -z "$confirmed_plan" ]]; then
    printf 'Cleanup requires a confirmed plan. Run with --dry-run first.\n' >&2
    exit 2
fi

hash_plan() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    else
        shasum -a 256 | awk '{print $1}'
    fi
}

contains_line() {
    local lines="$1"
    local expected="$2"
    [[ $'\n'"$lines"$'\n' == *$'\n'"$expected"$'\n'* ]]
}

running_container_ids=()
while IFS= read -r container_id; do
    running_container_ids+=("$container_id")
done < <(docker ps --quiet --no-trunc)
running_count="${#running_container_ids[@]}"

running_image_ids=""
if [[ ${#running_container_ids[@]} -gt 0 ]]; then
    running_image_ids="$(docker inspect --format '{{.Image}}' "${running_container_ids[@]}" | sort -u)"
fi

protected_image_id="$(docker image inspect --format '{{.Id}}' "$protected_image")"
unused_image_ids=()
while IFS= read -r image_id; do
    [[ -z "$image_id" ]] && continue
    if ! contains_line "$running_image_ids" "$image_id" && [[ "$image_id" != "$protected_image_id" ]]; then
        unused_image_ids+=("$image_id")
    fi
done < <(docker image ls --all --quiet --no-trunc | sort -u)

unused_network_ids=()
while IFS= read -r network_id; do
    [[ -z "$network_id" ]] && continue
    network_container_ids="$(docker network inspect \
        --format '{{range $id, $_ := .Containers}}{{println $id}}{{end}}' "$network_id" | sort -u)"
    network_has_running_container=false
    for container_id in "${running_container_ids[@]}"; do
        if contains_line "$network_container_ids" "$container_id"; then
            network_has_running_container=true
            break
        fi
    done
    if [[ "$network_has_running_container" == false ]]; then
        unused_network_ids+=("$network_id")
    fi
done < <(docker network ls --quiet --filter type=custom | sort -u)

running_volume_names=""
if [[ ${#running_container_ids[@]} -gt 0 ]]; then
    running_volume_names="$(docker inspect \
        --format '{{range .Mounts}}{{if eq .Type "volume"}}{{println .Name}}{{end}}{{end}}' \
        "${running_container_ids[@]}" | sort -u)"
fi

unused_volume_names=()
while IFS= read -r volume_name; do
    [[ -z "$volume_name" ]] && continue
    if ! contains_line "$running_volume_names" "$volume_name"; then
        unused_volume_names+=("$volume_name")
    fi
done < <(docker volume ls --quiet | sort -u)

stopped_container_ids="$(docker ps --all --quiet --no-trunc \
    --filter status=created --filter status=exited --filter status=dead | sort -u)"

plan_snapshot="$({
    printf 'protected-image=%s\n' "$protected_image_id"
    printf 'running='
    if [[ ${#running_container_ids[@]} -gt 0 ]]; then
        printf '%s\n' "${running_container_ids[@]}" | sort -u
    else
        printf '\n'
    fi
    printf 'stopped=%s\n' "$stopped_container_ids"
    printf 'images='
    if [[ ${#unused_image_ids[@]} -gt 0 ]]; then
        printf '%s\n' "${unused_image_ids[@]}" | sort -u
    else
        printf '\n'
    fi
    printf 'networks='
    if [[ ${#unused_network_ids[@]} -gt 0 ]]; then
        printf '%s\n' "${unused_network_ids[@]}" | sort -u
    else
        printf '\n'
    fi
    printf 'volumes='
    if [[ ${#unused_volume_names[@]} -gt 0 ]]; then
        printf '%s\n' "${unused_volume_names[@]}" | sort -u
    else
        printf '\n'
    fi
    docker system df
})"
plan_id="$(printf '%s' "$plan_snapshot" | hash_plan)"

printf 'Protected image: %s\n' "$protected_image"
printf 'Running containers protected: %s\n' "$running_count"
printf '\nStopped containers to delete:\n'
docker ps --all --filter status=created --filter status=exited --filter status=dead \
    --format '  {{.ID}}  {{.Names}}  {{.Status}}'

printf '\nUnused images to delete:\n'
if [[ ${#unused_image_ids[@]} -gt 0 ]]; then
    for image_id in "${unused_image_ids[@]}"; do
        docker image inspect --format '  {{.Id}}  {{if .RepoTags}}{{join .RepoTags ", "}}{{else}}<untagged>{{end}}' "$image_id"
    done
else
    printf '  None\n'
fi

printf '\nUnused networks to delete:\n'
if [[ ${#unused_network_ids[@]} -gt 0 ]]; then
    for network_id in "${unused_network_ids[@]}"; do
        docker network inspect --format '  {{slice .Id 0 12}}  {{.Name}}' "$network_id"
    done
else
    printf '  None\n'
fi

printf '\nUnused volumes to delete (data is not recoverable without a backup):\n'
if [[ ${#unused_volume_names[@]} -gt 0 ]]; then
    printf '  %s\n' "${unused_volume_names[@]}"
else
    printf '  None\n'
fi

printf '\nBuild cache eligible for deletion:\n'
docker builder du || true

printf '\nCurrent Docker disk usage:\n'
docker system df

printf '\nImpact and recovery:\n'
printf '  Containers: writable layer, logs, and config removed; recreate from image/Compose.\n'
printf '  Images: pull or rebuild if still available; local-only images may be unrecoverable.\n'
printf '  Networks: usually recreated by Compose; custom config may need manual recreation.\n'
printf '  Volumes: stored data permanently removed; restore only from an external backup.\n'
printf '  Build cache: only future build speed is affected; cache is regenerated by builds.\n'
printf '\nPlan ID: %s\n' "$plan_id"

if [[ "$dry_run" == true ]]; then
    printf 'Dry run only. Review this plan and obtain explicit user confirmation.\n'
    exit 0
fi

if [[ "$confirmed_plan" != "$plan_id" ]]; then
    printf 'Cleanup plan changed. Nothing was deleted. Review the new plan and confirm again.\n' >&2
    exit 3
fi

docker container prune --force

keeper_name="codex-keep-docker-image-$$"
docker create --name "$keeper_name" "$protected_image" >/dev/null

cleanup_keeper() {
    docker rm "$keeper_name" >/dev/null 2>&1 || true
}

trap cleanup_keeper EXIT

docker image prune --all --force
docker network prune --force
docker volume prune --all --force
docker builder prune --all --force

cleanup_keeper
trap - EXIT

if [[ ${#running_container_ids[@]} -gt 0 ]]; then
    for container_id in "${running_container_ids[@]}"; do
        if [[ "$(docker inspect --format '{{.State.Running}}' "$container_id" 2>/dev/null || true)" != true ]]; then
            printf 'Previously running container is no longer running: %s\n' "$container_id" >&2
            exit 1
        fi
    done
fi

docker image inspect "$protected_image" >/dev/null

printf 'Cleanup complete.\n'
printf 'Running containers preserved: %s\n' "$running_count"
printf 'Protected image preserved: %s\n' "$protected_image"
docker system df
