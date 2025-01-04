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

from cl.hackathon.one_step_solution import OneStepSolution


def test_get_trade_ids_list():
    solution = OneStepSolution(trade_group="Test")

    solution.trade_ids = "1-3"
    # Basic range
    assert solution.get_trade_ids_list() == [1, 2, 3]
    # Single number
    solution.trade_ids = "5"
    assert solution.get_trade_ids_list() == [5]
    # Combination of range and single number
    solution.trade_ids = "1-3, 5"
    assert solution.get_trade_ids_list() == [1, 2, 3, 5]
    # Multiple ranges and single numbers
    solution.trade_ids = "1-3, 5, 7-9"
    assert solution.get_trade_ids_list() == [1, 2, 3, 5, 7, 8, 9]
    # Overlapping ranges
    solution.trade_ids = "1-3, 2-4"
    assert solution.get_trade_ids_list() == [1, 2, 3, 4]
    # Empty input
    solution.trade_ids = ""
    assert solution.get_trade_ids_list() == []
    # Whitespaces around numbers and ranges
    solution.trade_ids = " 1 - 3 , 5 "
    assert solution.get_trade_ids_list() == [1, 2, 3, 5]
    # Same start and end in a range
    solution.trade_ids = "5-5, 1"
    assert solution.get_trade_ids_list() == [1, 5]
    # Test unsorted input
    solution.trade_ids = "5, 1-3"
    assert solution.get_trade_ids_list() == [1, 2, 3, 5]
