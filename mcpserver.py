from prefab_ui.app import PrefabApp
from prefab_ui.rx import Rx, RESULT, ERROR
from prefab_ui.components.charts import Sparkline
from prefab_ui.actions import SetState
from prefab_ui.actions.mcp import CallTool
from prefab_ui.components import (
    Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
    Column, Grid, GridItem, Markdown, Metric, P,
)
from fastmcp import FastMCP, FastMCPApp
from anthropic import Anthropic

import httpx
import time

from strava_auth import get_valid_access_token

app = FastMCPApp(
    "MyWorkoutAnalyticsServer"
    )

claude = Anthropic()

# Build function to retrieve workout data
async def _fetch_workout_data(days: int = 31) -> dict:
    token = await get_valid_access_token()
    after_timestamp = int(time.time() - days * 86400)

    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://www.strava.com/api/v3/athlete",
            headers={"Authorization": f"Bearer {token}"},
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()

        stats_resp = await client.get(
            f"https://www.strava.com/api/v3/athletes/{user_data['id']}/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        stats_resp.raise_for_status()
        user_stats = stats_resp.json()

        activities_resp = await client.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"after": after_timestamp},
        )
        activities_resp.raise_for_status()
        workouts = activities_resp.json()

    runs = [w for w in workouts if w.get("type") == "Run"]
    weights = [w for w in workouts if w.get("type") == "WeightTraining"]

    return {
        "user_data": user_data,
        "user_stats": user_stats,
        "runs": runs,
        "weights": weights
    }

# Ask Server to get recent workouts 
@app.tool()
async def get_recent_workouts(days: int = 31) -> PrefabApp:
    """Get user workouts for the last N days."""
    # How far back to retrieve workouts

    current_timestamp = int(time.time())
    after_timestamp = current_timestamp - (days*86400)

    # Authenticate to Strava API
    token = await get_valid_access_token()

    # Get user data
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.strava.com/api/v3/athlete",
            headers={"Authorization": f"Bearer {token}"},
        )

        user_data = response.json()
    
    # Get user stats
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://www.strava.com/api/v3/athletes/{user_data["id"]}/stats",
            headers={"Authorization": f"Bearer {token}"}
        )
        user_stats = response.json()

    # Get user activities for past N days
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"after": after_timestamp}
        )
        workouts = response.json()

    # Track Workout metrics
    workout_speed = []
    workout_distance = []
    workout_avg_hr = []
    workout_suffer_score = []

    # Iterate through workouts to collect data points
    for i in workouts:
        if i["type"] == "Run":
            # Convert Meters per Second to Miles per Hour and add to list
            workout_speed.append(i["average_speed"]*2.23694)

            # Convert Meters to Miles
            workout_distance.append((i["distance"]*3.28084)/5280)

            workout_avg_hr.append(i["average_heartrate"])
            workout_suffer_score.append(i["suffer_score"])

    # Define grid to hold objectss
    with Grid(columns={"default": 1, "md": 2, "lg": 4}, gap=6) as view:

        # Second and Third Column 
        with GridItem(css_class="md:col-span-2"):
            with Column(gap=4):
                with Grid(columns=2, gap=4):
                    with Card():
                        with CardContent(css_class="p-6"):
                            Metric(label="All Time Rides", value=f"{user_stats["all_ride_totals"]["count"]} Rides")
                    with Card():
                        with CardContent(css_class="p-6"):
                            Metric(label="All Time Ride Distance", value=f"{round((user_stats["all_ride_totals"]["distance"]*3.28084)/5280)} Miles")

                    with Card():
                        with CardContent(css_class="p-6"):
                            Metric(label="All Time Runs", value=f"{user_stats["all_run_totals"]["count"]}")
                    with Card():
                        with CardContent(css_class="p-6"):
                            Metric(label="All Time Run Distance", value=f"{round((user_stats["all_run_totals"]["distance"]*3.28084)/5280)} Miles")

                with Card():
                    with CardContent():
                        CardDescription(f"Past {days} days")
                        Metric(
                            label="Suffering Index",
                            value=f"{workout_suffer_score[-1]}",
                            delta=f"{workout_suffer_score[-1] - workout_suffer_score[0]}"
                        )
                        if workout_suffer_score[-1] - workout_suffer_score[0] > 0:
                            suffering_direction = "success"
                        else:
                            suffering_direction = "destructive"
                    Sparkline(
                        data = workout_suffer_score,
                        variant=suffering_direction,
                        fill=True,
                        css_class="h-16"
                    )  
    return PrefabApp(view=view)

# Define a tool to query Claude for a run recommendation with the context of recent workouts
@app.tool()
async def get_run_recommendation(days: int = 31) -> str:
    data = await _fetch_workout_data(days = 31)

    summary = [
        {
            "date": r["start_date_local"],
            "distance_mi": round((r["distance"] * 3.28084) / 5280, 1),
            "pace_mph": round(r["average_speed"] * 2.23694, 1),
            "avg_hr": r.get("average_heartrate"),
            "suffer_score": r.get("suffer_score"),
        }
        for r in data["runs"]
    ]

    response = claude.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=(
            "You are a running coach. Given a list of recent runs for a 29 year old athlete, recommend what "
            "today's run should be (rest, speed, distance) and explain why in a paragraph or two. "
            "Include Heart Rate ranges and any other helpful information."
        ),
        messages=[{"role": "user", "content": f"Recent Runs (last {days} days): {summary}"}]
    )

    # Parse out the response from the model
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks) if text_blocks else "No response generated."

# Build UI for server showing workouts and run recommendations
@app.ui()
async def dashboard(days: int = 31) -> PrefabApp:
    data = await _fetch_workout_data(days=days)

    user_data = data["user_data"]
    user_stats = data["user_stats"]
    runs = data["runs"]
    # weights = data["weights"]

    suffer_scores = [r["suffer_score"] for r in runs if r.get("suffer_score") is not None]
    suffering_direction = "success"

    if len(suffer_scores) >= 2 and (suffer_scores[-1] - suffer_scores[0]) <= 0:
        suffering_direction = "destructive"

    loading = Rx("loading")

    with PrefabApp(state={"loading": False, "recommendation": ""}) as view:
        with Grid(columns={"default": 1, "md": 2, "lg": 4}, gap=6):
            
            
            # Column 1: User data
            with Column():
                with Card():
                    with CardHeader():
                        CardTitle(f"User {user_data["firstname"]}")
                        CardDescription(f"Logged in as user {user_data["id"]}")
                    with CardContent():
                        P(f"{user_data["firstname"]} has had an account since {user_data["created_at"]} and last uploaded a workout on {user_data["updated_at"]}.")
                
            # Column 2-3: All time metrics and suffer scores
            with GridItem(css_class="md:col-span-2"):
                with Column(gap=4):
                    with Grid(columns=4, gap=4, css_class="h-32"):
                        with Card():
                            with CardContent(css_class="p-6"):
                                Metric(label="All Time Rides",
                                    value=f"{user_stats['all_ride_totals']['count']} Rides")
                        with Card():
                            with CardContent(css_class="p-6"):
                                Metric(label="All Time Ride Distance",
                                    value=f"{round((user_stats['all_ride_totals']['distance']*3.28084)/5280)} Miles")
                        with Card():
                            with CardContent(css_class="p-6"):
                                Metric(label="All Time Runs",
                                    value=f"{user_stats['all_run_totals']['count']}")
                        with Card():
                            with CardContent(css_class="p-6"):
                                Metric(label="All Time Run Distance",
                                    value=f"{round((user_stats['all_run_totals']['distance']*3.28084)/5280)} Miles")

                    if suffer_scores:
                        with Card(css_class="pb-0 gap-0"):
                            with CardContent():
                                CardDescription(f"Past {days} days")
                                Metric(
                                    label="Suffering Index",
                                    value=f"{suffer_scores[-1]}",
                                    delta=f"{suffer_scores[-1] - suffer_scores[0]}",
                                )
                            Sparkline(data=suffer_scores, variant=suffering_direction,
                                    fill=True, css_class="h-16")

            # Column 4: Run recommendation                
            with Column():
                with Card():
                    with CardHeader():
                        CardTitle("Today's Recommended Run")
                    with CardContent():
                        with Column(gap=3):
                            Button(
                                loading.then("Thinking...", "Get Recommendation"),
                                disabled=loading,
                                on_click=[
                                    SetState("loading", True),
                                    CallTool(
                                        "get_run_recommendation",
                                        on_success=[
                                            SetState("loading", False),
                                            SetState("recommendation", RESULT),
                                        ],
                                        on_error=[
                                            SetState("loading", False),
                                            SetState("recommendation", "Couldn't reach Claude. Try again."),
                                        ],
                                    ),
                                ],
                            )
                            Markdown("{{ recommendation }}")
    return view

mcp = FastMCP("MyWorkoutAnalyticsServer", providers=[app])

if __name__ == "__main__":
    mcp.run()