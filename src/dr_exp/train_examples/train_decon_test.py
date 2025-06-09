#!/usr/bin/env python3
"""
Test script for deconCNN integration with dr_exp
Minimal training script for testing the job management system
"""

import hydra
from omegaconf import DictConfig
from deconcnn import create_cifar10_training_components, train_model


@hydra.main(version_base=None, config_path="configs", config_name="decon_test_config")
def main(cfg: DictConfig) -> None:
    """
    Main training function using deconCNN library
    """
    print(f"Starting training with config: {cfg.project_name}")
    print(f"Experiment: {cfg.experiment_name}")
    print(
        f"Model: {cfg.model.name}, Epochs: {cfg.epochs}, Batch size: {cfg.batch_size}"
    )

    # Create training components using deconCNN factory
    model, data_module, trainer = create_cifar10_training_components(cfg)

    # Run training
    train_model(trainer, model, data_module, cfg)

    print("Training completed successfully!")


if __name__ == "__main__":
    main()
