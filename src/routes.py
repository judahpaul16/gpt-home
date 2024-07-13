from semantic_router import Route
from semantic_router.encoders import OpenAIEncoder
from semantic_router.layer import RouteLayer

alarm_route = Route(
    name="alarm",
    utterances=[
        "set an alarm",
        "wake me up",
        "remind me in"
    ]
)

spotify_route = Route(
    name="spotify",
    utterances=[
        "play some music",
        "open spotify",
        "play my playlist"
    ]
)

weather_route = Route(
    name="weather",
    utterances=[
        "what's the weather",
        "tell me the weather",
        "forecast for today"
    ]
)

lights_route = Route(
    name="lights",
    utterances=[
        "turn on the lights",
        "switch off the lights",
        "dim the lights"
    ]
)

calendar_route = Route(
    name="calendar",
    utterances=[
        "schedule a meeting",
        "what's on my calendar",
        "add an event"
    ]
)

general_route = Route(
    name="general",
    utterances=[
        "tell me a joke",
        "what's the time",
        "how are you"
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
        return result.name if result else "other"

class Action:
    def __init__(self, action_name, text):
        self.action_name = action_name
        self.text = text

    async def perform(self, **kwargs):
        action_func = globals()[self.action_name]
        return await action_func(self.text, **kwargs)

async def action_router(text: str, display, router=ActionRouter()):
    action_name = router.resolve(text)
    act = Action(action_name, text)
    await act.perform(display=display)
