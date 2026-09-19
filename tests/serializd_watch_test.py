from serializd import (
    find_in_watched_library,
    get_season,
    mark_episode_watched,
)


def main():
    show_query = "The Boys"
    season_number = 1
    episode_number = 2

    print("WAYMARK Serializd watched-state test")
    print("This will perform ONE real Serializd write.")
    print(f"Target: {show_query} S{season_number:02d}E{episode_number:02d}")

    matches = find_in_watched_library(show_query)

    if not matches:
        print("Could not find The Boys in your watched library.")
        return

    show = matches[0]
    show_id = int(show["showId"])
    show_name = show.get("showName", show_query)

    print(f"Show: {show_name}")
    print(f"Serializd show ID: {show_id}")

    season = get_season(show_id, season_number)
    season_id = int(season["seasonId"])

    episode = next(
        (
            item
            for item in season.get("episodes", [])
            if int(item.get("episodeNumber", -1)) == episode_number
        ),
        None,
    )

    if episode is None:
        print("Episode was not found.")
        return

    print(f"Season ID: {season_id}")
    print(f"Episode: {episode.get('name', 'Unknown')}")
    print(f"Episode ID: {episode.get('episodeId', 'Unknown')}")

    print("\nMarking ONLY this episode as watched...")

    result = mark_episode_watched(
        show_id=show_id,
        season_id=season_id,
        episode_number=episode_number,
    )

    print("Write request succeeded. ✅")
    print("Response:")
    print(result)
    print("\nSTOP HERE. Do not run this script again.")
    print("We will verify the state and then remove the test entry safely.")


if __name__ == "__main__":
    main()
