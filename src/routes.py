from semantic_router import Route
from semantic_router.encoders import OpenAIEncoder
from semantic_router.layer import RouteLayer

from actions import *

alarm_route = Route(
    name="alarm_reminder_action",
    utterances=[
        "set an alarm",
        "wake me up",
        "remind me in"
    ]
)

spotify_route = Route(
    name="spotify_action",
    utterances=[
        "play some music",
        "open spotify",
        "play my playlist"
    ]
)

weather_route = Route(
    name="open_weather_action",
    utterances=[
        "what's the weather",
        "tell me the weather",
        "forecast for today"
    ]
)

lights_route = Route(
    name="philips_hue_action",
    utterances=[
        "turn on the lights",
        "switch off the lights",
        "dim the lights"
    ]
)

calendar_route = Route(
    name="caldav_action",
    utterances=[
        "schedule a meeting",
        "what's on my calendar",
        "add an event"
    ]
)

general_route = Route(
    name="query_openai",
    utterances=[
        "tell me a joke",
        "what's the time",
        "how are you",
        "what is the meaning of life",
        "what is the capital of France",
        "what is the difference between Python 2 and Python 3",
        "what is the best programming language",
        "who was the first president of the United States",
        "what is the largest mammal"
    ]
)

routes = [alarm_route, spotify_route, weather_route, lights_route, calendar_route, general_route]
encoder = OpenAIEncoder()
rl = RouteLayer(encoder=encoder, routes=routes)

class ActionRouter:
    def __init__(self):
        self.route_layer = rl

    def resolve(self, text):
        result = self.route_layer(text)
        return result.name if result else "query_openai"

class Action:
    def __init__(self, action_name, text):
        self.action_name = action_name
        self.text = text

    async def perform(self, **kwargs):
        action_func = globals()[self.action_name]
        return await action_func(self.text, **kwargs)

async def action_router(text: str, router=ActionRouter()):
    action_name = router.resolve(text)
    act = Action(action_name, text)
    return await act.perform()
