# SPDX-License-Identifier: AGPL-3.0-only
# Embedded in catalogue manifests that install a server through SteamCMD.
# A package passes a dedicated-server app ID and either linux or windows.
nex_steamcmd_update() {
  local app_id="$1" platform="$2"
  local archive attempt architecture steamclient
  local -a update=(+@ShutdownOnFailedCommand 1 +@NoPromptForPassword 1)

  cd "$HOME"
  mkdir -p steamcmd serverfiles
  if [[ ! -x steamcmd/steamcmd.sh ]]; then
    archive=$(mktemp)
    if ! curl --fail --silent --show-error --location --retry 3 \
      https://media.steampowered.com/client/steamcmd_linux.tar.gz -o "$archive" \
      || ! tar -xzf "$archive" -C steamcmd; then
      rm -f "$archive"
      return 1
    fi
    rm -f "$archive"
  fi

  if [[ "$platform" == windows ]]; then
    update+=(+@sSteamCmdForcePlatformType windows)
  fi
  update+=(+force_install_dir "$HOME/serverfiles" +login anonymous +app_update "$app_id" +quit)

  for attempt in 1 2 3; do
    if ./steamcmd/steamcmd.sh "${update[@]}"; then
      break
    fi
    if [[ "$attempt" == 3 ]]; then
      return 1
    fi
    sleep "$((attempt * 5))"
  done

  for architecture in 32 64; do
    steamclient="$HOME/steamcmd/linux$architecture/steamclient.so"
    if [[ -f "$steamclient" ]]; then
      mkdir -p ".steam/sdk$architecture"
      ln -sfn "$steamclient" ".steam/sdk$architecture/steamclient.so"
    fi
  done
  cd serverfiles
}
