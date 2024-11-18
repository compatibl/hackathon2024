import openai
from openai import OpenAI
from dotenv import find_dotenv
from dotenv import load_dotenv
import os
import yaml
from cl.runtime.settings.project_settings import ProjectSettings


class GPTClient:
    MODEL = "gpt-4o-mini"

    def __init__(self):
        self.client = OpenAI(api_key=GPTClient.get_openai_key())

    @staticmethod
    def get_openai_key():
        secrets_path = os.path.normpath(os.path.join(ProjectSettings.get_project_root(), ".secrets.yaml"))
        with open(secrets_path, 'r') as file:
            secrets = yaml.safe_load(file)
        # Retrieve the key under 'default' -> 'openai_key'
        openai_key = secrets.get('default', {}).get('openai_api_key')
        if openai_key:
            print("OpenAI API Key retrieved successfully!")
        else:
            print("OpenAI API Key not found. Please check your .env file.")
        return openai_key


    def ensure_validity(self, context: str, assistant_prompt: str) -> bool:
        answer = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {"role": "system", "content": "You are a quant trained in identifying the trade parameters. "
                                              "You will be given a trade description, and a description of a trade attribute that was meant to be provided."
                                              "Then, you will be given this trade attribute as an identified value: you are meant to validate if this value is irght for a given trade description."
                                              "Return your answer as a 'yes' for right answer and 'no' for wrong. If the parameter is not possible to be identified, return 'not given'."},
                {
                    "role": "user",
                    "content": context
                },
                {
                    "role": "assistant",
                    "content": assistant_prompt
                },
            ]
        )
        decision = answer.choices[0].message.content

        if 'yes' in decision.lower():
            output = True
        elif 'no' in decision.lower():
            output = False
        elif 'not given' in decision.lower():
            output = False
        else:
            print(f"Wrong answer: {decision}")
            output = False
        print(f"Result: {output} for answer: {assistant_prompt} and query: {context}.")
        return output
