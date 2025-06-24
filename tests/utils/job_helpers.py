def create_test_job(job_db, priority=100, **kwargs):
    config = {
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10,
        **kwargs
    }
    return job_db.create_job(config, priority=priority)

def create_test_config(**overrides):
    base = {
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10,
        "lr": 0.001
    }
    base.update(overrides)
    return base

def create_multiple_jobs(job_db, count, priority_start=100, priority_step=50):
    job_ids = []
    for i in range(count):
        job_id = create_test_job(
            job_db, 
            priority=priority_start + i * priority_step,
            index=i
        )
        job_ids.append(job_id)
    return job_ids