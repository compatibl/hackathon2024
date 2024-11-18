# Copyright (C) 2023-present The Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from dataclasses import dataclass
from typing import List

from markdown_it.common.html_re import attribute
from typing_extensions import Self
from cl.runtime import Context
from cl.runtime.experiments.trial_key import TrialKey
from cl.runtime.log.exceptions.user_error import UserError
from cl.runtime.primitive.bool_util import BoolUtil
from cl.runtime.primitive.string_util import StringUtil
from cl.runtime.records.dataclasses_extensions import missing
from cl.convince.entries.entry import Entry
from cl.convince.llms.gpt.gpt_llm import GptLlm
from cl.convince.llms.llm import Llm
from cl.convince.llms.llm_key import LlmKey
from cl.convince.prompts.formatted_prompt import FormattedPrompt
from cl.convince.prompts.prompt import Prompt
from cl.convince.prompts.prompt_key import PromptKey
from cl.convince.retrievers.annotating_retrieval import AnnotatingRetrieval
from cl.convince.retrievers.retrieval import Retrieval
from cl.convince.retrievers.retriever import Retriever
from cl.convince.retrievers.retriever_util import RetrieverUtil

_TRIPLE_BACKTICKS_RE = re.compile(r"```(.*?)```", re.DOTALL)
"""Regex for text between triple backticks."""

_BRACES_RE = re.compile(r"\{(.*?)\}")
"""Regex for text between curly braces."""

_TEMPLATE = """You will be provided with an input text and a description of a parameter.
Your goal is to surround each piece of information about this parameter you find in the input text by curly braces.
Use multiple non-nested pairs of opening and closing curly braces if you find more than one piece of information.

You must reply with JSON formatted strictly according to the JSON specification in which all values are strings.
The JSON must have the following keys:

{{
    "success": <Y if at least one piece of information was found and N otherwise. This parameter is required.>
    "annotated_text": "<The input text where each piece of information about this parameter is surrounded by curly braces. There should be no changes other than adding curly braces, even to whitespace. Leave this field empty in case of failure.>,"
    "justification": "<Justification for your annotations in case of success or the reason why you were not able to find the parameter in case of failure.>"
}}
Input text: ```{InputText}```
Parameter description: ```{ParamDescription}```
"""


@dataclass(slots=True, kw_only=True)
class AnnotatingRetriever(Retriever):
    """Instructs the model to surround the requested parameter by curly braces and uses the annotations to retrieve."""

    MAX_CALLS = 50

    prompt: PromptKey = missing()
    """Prompt used to perform the retrieval."""

    max_retries: int = missing()
    """How many times to retry the annotation in case changes other than braces are detected."""

    call_count: int = 0
    """How many times the LLM has been called"""

    def init(self) -> Self:
        """Similar to __init__ but can use fields set after construction, return self to enable method chaining."""
        if self.prompt is None:
            self.prompt = FormattedPrompt(
                prompt_id="AnnotatingRetriever",
                params_type=Retrieval.__name__,
                template=_TEMPLATE,
            )  # TODO: Review the handling of defaults

        # Default max_retries
        if self.max_retries is None:
            self.max_retries = 1

        self.call_count = 0

        # Return self to enable method chaining
        return self

    @property
    def calls_remaining(self) -> int:
        """number of calls remaining"""
        return self.MAX_CALLS - self.call_count

    def retrieve(
        self,
        *,
        input_text: str,
        param_description: str,
        is_required: bool = False,  # TODO: Make this parameter required
        param_samples: List[str] | None = None,
    ) -> str | None:
        self.call_count += 1

        # Load the full LLM specified by the context
        context = Context.current()
        llm = context.load_one(Llm, context.full_llm)

        # Load the prompt
        prompt = context.load_one(Prompt, self.prompt)

        # Run multiple retries
        for retry_index in range(self.max_retries):
            is_last_trial = retry_index == self.max_retries - 1

            # Append retry_index to trial_id to avoid reusing a cached completion
            if self.max_retries > 1:
                context = Context.current()
                if context.trial is not None:
                    trial_key = TrialKey(trial_id=f"{context.trial.trial_id}\\{retry_index}")
                else:
                    trial_key = TrialKey(trial_id=str(retry_index))
            else:
                trial_key = context.trial
            with Context(trial=trial_key) as context:

                # Strip starting and ending whitespace
                input_text = input_text.strip()  # TODO: Perform more advanced normalization

                # Create a retrieval record and populate it with inputs, each trial will have a new one
                retrieval = AnnotatingRetrieval(
                    retriever=self.get_key(),
                    trial=context.trial,
                    input_text=input_text,
                    param_description=param_description,
                    is_required=is_required,
                    param_samples=param_samples,
                )
                try:
                    # Create a brace extraction prompt using input parameters
                    rendered_prompt = prompt.render(params=retrieval)

                    # Get text annotated with braces and check that the only difference is braces and whitespace
                    completion = llm.completion(rendered_prompt)

                    # Extract the results
                    json_result = RetrieverUtil.extract_json(completion)
                    if json_result is not None:
                        retrieval.success = json_result.get("success", None)
                        retrieval.annotated_text = json_result.get("annotated_text", None)
                        retrieval.justification = json_result.get("justification", None)
                        context.save_one(retrieval)
                    else:
                        retrieval.success = "N"
                        retrieval.justification = (
                            f"Could not extract JSON from the LLM response. " f"LLM response:\n{completion}\n"
                        )
                        context.save_one(retrieval)
                        raise UserError(retrieval.justification)

                    # Return None if not found
                    success = BoolUtil.parse_required_bool(retrieval.success, field_name="success")
                    if not success:
                        # Parameter is not found
                        if is_required:
                            # Required, continue with the next trial
                            continue
                        else:
                            # Optional, return None
                            return None

                    if StringUtil.is_not_empty(retrieval.annotated_text):
                        # Compare after removing the curly brackets
                        to_compare = self._deannotate(retrieval.annotated_text)
                        if to_compare != input_text:
                            if not is_last_trial:
                                # Continue if not the last trial
                                continue
                            else:
                                # Otherwise report an error
                                # TODO: Use unified diff
                                raise UserError(
                                    f"Annotated text has changes other than curly braces.\n"
                                    f"Input text: ```{input_text}```\n"
                                    f"Annotated text: ```{retrieval.annotated_text}```\n"
                                )
                    else:
                        raise RuntimeError(
                            f"Extraction success reported by {llm.llm_id}, however "
                            f"the annotated text is empty. Input text:\n{input_text}\n"
                        )

                    # Extract data inside braces
                    matches = re.findall(_BRACES_RE, retrieval.annotated_text)
                    for match in matches:
                        if "{" in match or "}" in match:
                            if not is_last_trial:
                                continue
                            else:
                                raise UserError(
                                    f"Nested curly braces are present in annotated text.\n"
                                    f"Annotated text: ```{retrieval.annotated_text}```\n"
                                )

                    # Combine and return from inside the loop
                    # TODO: Determine if numbered combination works better
                    retrieval.output_text = " ".join(matches)
                    context.save_one(retrieval)

                    # Return only the parameter value
                    return retrieval.output_text

                except Exception as e:
                    if is_last_trial:
                        # Rethrow only when the last trial is reached
                        retrieval.success = "N"
                        retrieval.justification = str(e)
                        context.save_one(retrieval)
                        raise UserError(
                            f"Unable to extract parameter from the input text after {self.max_retries} retries.\n"
                            f"Input text: {input_text}\n"
                            f"Parameter description: {param_description}\n"
                            f"Last trial error information: {str(e)}\n"
                        )
                    else:
                        # Otherwise continue
                        pass

        # The method should always return from the loop, adding as a backup in case this changes in the future
        raise UserError(
            f"Unable to extract parameter from the input text.\n"
            f"Input text: {input_text}\n"
            f"Parameter description: {param_description}\n"
        )

    @classmethod
    def _extract_annotated(cls, text: str) -> str:
        # Find all occurrences of triple backticks and the text inside them
        matches = re.findall(_TRIPLE_BACKTICKS_RE, text)
        if len(matches) == 0:
            raise RuntimeError("No string found between triple backticks in: ", text)
        elif len(matches) > 1:
            raise RuntimeError("More than one string found between triple backticks in: ", text)
        result = matches[0].strip()
        return result

    @classmethod
    def _extract_in_braces(
        cls, annotated_text: str, *, continue_on_error: bool | None = None
    ) -> str | None:  # TODO: Move to Util class
        """
        Extract the blocks inside curly braces.

        Notes:
            - Return as semicolon-delimited string if more than one block is found
            - If continue_on_error is True, return None without raising an error
        """
        matches = re.findall(_BRACES_RE, annotated_text)
        if len(matches) == 0:
            if continue_on_error:
                return None
            else:
                raise UserError(
                    f"No curly braces are present in annotated text.\n" f"Annotated text: ```{annotated_text}```\n"
                )
        if any("{" in match or "}" in match for match in matches):
            if continue_on_error:
                return None
            else:
                raise UserError(
                    f"Nested curly braces are present in annotated text.\n" f"Annotated text: ```{annotated_text}```\n"
                )

        # Combine using semicolon delimiter and return
        result = ";".join(matches)
        return result

    @classmethod
    def _deannotate(cls, text: str) -> str:
        # Remove triple backticks and curly brackets
        result = text.replace("`", "").strip().replace("{", "").replace("}", "").strip()
        return result
