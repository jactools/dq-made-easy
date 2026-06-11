import ast
import json
import os
from typing import Iterable
from typing import Callable

from confection import Config
from confection import SimpleFrozenDict
from spacy_llm.models.hf.base import HuggingFace
from spacy_llm.registry.util import registry
from spacy_llm.util import assemble_from_config
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig


MODEL_ID = os.getenv("DQ_LLM_MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")
DEVICE_MAP = os.getenv("DQ_LLM_DEVICE_MAP", "auto")
MAX_NEW_TOKENS = int(os.getenv("DQ_LLM_MAX_NEW_TOKENS", "512"))


class GenericChatHuggingFace(HuggingFace):
    def __init__(
        self,
        name,
        config_init=None,
        config_run=None,
        context_length=None,
    ):
        self._tokenizer = None
        super().__init__(name, config_init, config_run, context_length)
        self._hf_config_run = GenerationConfig(**self._config_run)

    def _check_model(self) -> None:
        return None

    @property
    def hf_account(self) -> str:
        return ""

    def init_model(self):
        self._tokenizer = AutoTokenizer.from_pretrained(self._name)
        init_cfg = self._config_init
        device = None
        if "device" in init_cfg:
            device = init_cfg.pop("device")

        model = AutoModelForCausalLM.from_pretrained(
            self._name, **init_cfg, resume_download=True
        )
        if device:
            model.to(device)

        return model

    def _tokenize_prompt(self, prompt_text: str):
        encoding = self._tokenizer(
            prompt_text,
            return_tensors="pt",
            return_attention_mask=True,
        )
        return {
            "input_ids": encoding.input_ids.to(self._model.device),
            "attention_mask": encoding.attention_mask.to(self._model.device),
        }

    def __call__(self, prompts: Iterable[Iterable[str]]) -> Iterable[Iterable[str]]:
        assert self._tokenizer is not None
        assert hasattr(self._model, "generate")

        responses = []
        chat_template = getattr(self._tokenizer, "apply_chat_template", None)

        for prompts_for_doc in prompts:
            prompts_for_doc = list(prompts_for_doc)
            tokenized_input_ids = []

            for prompt in prompts_for_doc:
                if callable(chat_template):
                    prompt_text = chat_template(
                        [{"role": "user", "content": prompt}],
                        tokenize=False,
                        add_generation_prompt=True,
                    )
                else:
                    prompt_text = prompt

                tokenized_input_ids.append(self._tokenize_prompt(prompt_text))

            responses.append(
                [
                    self._tokenizer.decode(
                        self._model.generate(
                            input_ids=tokenized_inputs["input_ids"],
                            attention_mask=tokenized_inputs["attention_mask"],
                            generation_config=self._hf_config_run,
                        )[:, tokenized_inputs["input_ids"].shape[1] :][0],
                        skip_special_tokens=True,
                    )
                    for tokenized_inputs in tokenized_input_ids
                ]
            )

        return responses


def _coerce_config_mapping(value, field_name: str):
    if value is None:
        return {}

    if isinstance(value, (dict, SimpleFrozenDict)):
        return dict(value)

    if isinstance(value, str):
        try:
            parsed_value = ast.literal_eval(value)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"{field_name} must be a dict-like value") from exc

        if isinstance(parsed_value, dict):
            return parsed_value

    raise TypeError(f"{field_name} must be a dict, got {type(value).__name__}")


@registry.llm_models("dq.HFChat.v1")
def generic_chat_hf(
    name,
    config_init: object = SimpleFrozenDict(),
    config_run: object = SimpleFrozenDict(),
) -> Callable[[Iterable[Iterable[str]]], Iterable[Iterable[str]]]:
    model = GenericChatHuggingFace(
        name=name,
        config_init=_coerce_config_mapping(config_init, "config_init"),
        config_run=_coerce_config_mapping(config_run, "config_run"),
        context_length=8000,
    )

    def execute(prompts: Iterable[Iterable[str]]) -> Iterable[Iterable[str]]:
        return model(prompts)

    return execute


def main() -> None:
    config = Config().from_str(
        f"""
[nlp]
lang = "en"
pipeline = ["llm"]

[components]

[components.llm]
factory = "llm"

[components.llm.task]
@llm_tasks = "spacy.Raw.v1"
field = "llm_raw_output"

[components.llm.task.template]
@misc = "spacy.FileReader.v1"
path = "extract_rules_prompt.jinja2"

[components.llm.model]
@llm_models = "dq.HFChat.v1"
name = {json.dumps(MODEL_ID)}
config_init = {{"device_map": {json.dumps(DEVICE_MAP)}}}
config_run = {{"max_new_tokens": {MAX_NEW_TOKENS}}}
"""
    )
    assemble_from_config(config)


if __name__ == "__main__":
    main()
