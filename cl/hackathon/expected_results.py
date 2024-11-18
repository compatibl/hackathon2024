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

from dataclasses import dataclass
from typing_extensions import Self
from cl.runtime.log.exceptions.user_error import UserError
from cl.convince.llms.llm_key import LlmKey
from cl.hackathon.hackathon_input import HackathonInput
from cl.hackathon.hackathon_output import HackathonOutput
from cl.hackathon.hackathon_solution import HackathonSolution


@dataclass(slots=True, kw_only=True)
class ExpectedResults(HackathonSolution):
    """Solution key under which the expected (correct) outputs are recorded."""

    def generate_output(self, output_: HackathonOutput) -> None:
        """Run scoring on the output."""
        raise UserError(
            "Solution ExpectedResults is used only to hold the expected results for "
            "scoring other methods. It does not have a its own scoring method."
        )

    def init(self) -> Self:
        """Similar to __init__ but can use fields set after construction, return self to enable method chaining."""
        self.llm = LlmKey(llm_id="Not required")

        # Return self to enable method chaining
        return self
