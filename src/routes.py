from semantic_router.layer import RouteLayer
import semantic_router.encoders as encoders
from semantic_router import Route

from actions import *

API_KEY = os.getenv("OPENAI_API_KEY")
encoder = encoders.OpenAIEncoder(openai_api_key=API_KEY)

# Define routes
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
        "next song",
        "pause the music",
        "play earth wind and fire on Spotify",
        "play my playlist"
    ]
)

weather_route = Route(
    name="open_weather_action",
    utterances=[
        "what's the weather",
        "tell me the weather",
        "what is the temperature",
        "is it going to rain",
        "how is the weather in New York"
    ]
)

lights_route = Route(
    name="philips_hue_action",
    utterances=[
        "turn on the lights",
        "switch off the lights",
        "dim the lights",
        "change the color of the lights",
        "set the lights to red"
    ]
)

calendar_route = Route(
    name="caldav_action",
    utterances=[
        "schedule a meeting",
        "what's on my calendar",
        "add an event",
        "what is left to do today"
    ]
)

general_route = Route(
    name="llm_action",
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

# Initialize RouteLayer with the encoder and routes
rl = RouteLayer(encoder=encoder, routes=routes)

class ActionRouter:
    def __init__(self):
        self.route_layer = rl

    def resolve(self, text):
        logger.info(f"Resolving text: {text}")
        try:
            result = self.route_layer(text)
            action_name = result.name if result else "llm_action"
            logger.info(f"Resolved action: {action_name}")
            return action_name
        except Exception as e:
            logger.error(f"Error resolving text: {e}")
            return "llm_action"

class Action:
    def __init__(self, action_name, text):
        self.action_name = action_name
        self.text = text

    async def perform(self, **kwargs):
        try:
            action_func = globals()[self.action_name]
            logger.info(f"Performing action: {self.action_name} with text: {self.text}")
            return await action_func(self.text, **kwargs)
        except KeyError:
            logger.warning(f"Action {self.action_name} not found. Falling back to llm_action.")
            action_func = globals()["llm_action"]
            return await action_func(self.text, **kwargs)
        except Exception as e:
            logger.error(f"Error performing action {self.action_name}: {e}")
            return "Action failed due to an error."

async def action_router(text: str, router=ActionRouter()):
    try:
        action_name = router.resolve(text)
        act = Action(action_name, text)
        return await act.perform()
    except Exception as e:
        logger.error(f"Error in action_router: {e}")
        return "Action routing failed due to an error."