from medpar_qa.manifest import load_manifest
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.orchestration.pipeline import Pipeline


def test_all_stages_example_manifest_passes():
    manifest = load_manifest("config/run_manifest.all_stages.example.yaml")
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    results = Pipeline(manifest, resolver).run()
    assert [result.stage.value for result in results] == [
        "final_action",
        "split",
        "stay",
        "intermediate",
        "final_medpar",
    ]
    assert all(result.passed for result in results)
