"""Property-based tests for IntentJSON data model.

Validates: Requirements 2.1, 2.5
"""

from dataclasses import asdict, fields

import hypothesis.strategies as st
from hypothesis import given, settings

from backend.models.intent import IntentJSON

# Strategy for valid cloud providers
cloud_strategy = st.sampled_from(["AWS", "Azure", "GCP"])

# Strategy for non-empty strings (intent and action fields)
non_empty_str_strategy = st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != "")

# Strategy for conditions (can be empty)
conditions_strategy = st.text(min_size=0, max_size=500)

# Composite strategy to generate valid IntentJSON objects
intent_json_strategy = st.builds(
    IntentJSON,
    intent=non_empty_str_strategy,
    cloud=cloud_strategy,
    action=non_empty_str_strategy,
    conditions=conditions_strategy,
)


class TestProperty2IntentJSONStructuralInvariant:
    """Property 2: Intent_JSON structural invariant.

    Generate random IntentJSON objects and verify all four fields are present
    with correct types.

    Validates: Requirements 2.1, 2.5
    """

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_all_four_fields_present(self, intent: IntentJSON) -> None:
        """All IntentJSON objects must have exactly four fields."""
        field_names = {f.name for f in fields(intent)}
        assert field_names == {"intent", "cloud", "action", "conditions"}

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_intent_field_is_non_empty_string(self, intent: IntentJSON) -> None:
        """The intent field must be a non-empty string."""
        assert isinstance(intent.intent, str)
        assert len(intent.intent) > 0

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_cloud_field_is_valid_provider(self, intent: IntentJSON) -> None:
        """The cloud field must be one of AWS, Azure, or GCP."""
        assert isinstance(intent.cloud, str)
        assert intent.cloud in {"AWS", "Azure", "GCP"}

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_action_field_is_non_empty_string(self, intent: IntentJSON) -> None:
        """The action field must be a non-empty string."""
        assert isinstance(intent.action, str)
        assert len(intent.action) > 0

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_conditions_field_is_string(self, intent: IntentJSON) -> None:
        """The conditions field must be a string (may be empty)."""
        assert isinstance(intent.conditions, str)


class TestProperty3IntentJSONRoundTrip:
    """Property 3: Intent_JSON round-trip.

    Serialize and deserialize IntentJSON, verify equivalence.

    Validates: Requirements 2.1, 2.5
    """

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_serialize_deserialize_equivalence(self, intent: IntentJSON) -> None:
        """Serializing to dict and back must produce an equal IntentJSON."""
        serialized = asdict(intent)
        deserialized = IntentJSON(**serialized)
        assert deserialized == intent

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_serialized_dict_has_all_fields(self, intent: IntentJSON) -> None:
        """The serialized dict must contain all four field keys."""
        serialized = asdict(intent)
        assert set(serialized.keys()) == {"intent", "cloud", "action", "conditions"}

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_serialized_values_match_original(self, intent: IntentJSON) -> None:
        """Each value in the serialized dict must match the original field."""
        serialized = asdict(intent)
        assert serialized["intent"] == intent.intent
        assert serialized["cloud"] == intent.cloud
        assert serialized["action"] == intent.action
        assert serialized["conditions"] == intent.conditions

    @settings(max_examples=100)
    @given(intent=intent_json_strategy)
    def test_round_trip_preserves_types(self, intent: IntentJSON) -> None:
        """After round-trip, all field types must be preserved."""
        serialized = asdict(intent)
        deserialized = IntentJSON(**serialized)
        assert isinstance(deserialized.intent, str)
        assert isinstance(deserialized.cloud, str)
        assert isinstance(deserialized.action, str)
        assert isinstance(deserialized.conditions, str)
