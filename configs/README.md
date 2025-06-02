# Configurations

This folder contains Hydra configuration files used to define experiments.

- `config.yaml` is the base configuration loaded by Hydra.
- `model/` holds model-specific settings such as `resnet.yaml` and `vit.yaml`.
- `optim/` stores optimizer settings like `adam.yaml`, `adamw.yaml`, and `sgd.yaml`.

These YAML files are combined to produce fully resolved experiment configs that are uploaded to Supabase.
