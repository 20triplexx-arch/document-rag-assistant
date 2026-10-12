"""Maintainer-only routes, using existing authentication and CSRF checks."""
from pathlib import Path
from threading import Lock
from contextlib import asynccontextmanager
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from .lab import Lab
from .lab_models import ClaimReview, DatasetReview, ExperimentConfig, ImportRequest


def register_lab_routes(app, current_user, data_dir, user_store, model):
    creation_lock=Lock()

    def maintainer(user=Depends(current_user)):
        if user["role"] != "admin":
            raise HTTPException(403,"质量诊断工作台仅供维护者使用。")
        return user

    def lab():
        with creation_lock:
            if not hasattr(app.state,"lab"):
                app.state.lab=Lab(data_dir,user_store.path.parent / "experiments.sqlite3",model=model)
            return app.state.lab

    def checked(action):
        try:
            return action()
        except KeyError:
            raise HTTPException(404,"实验或题集不存在。") from None
        except (ValueError,OSError) as error:
            raise HTTPException(409,str(error) if isinstance(error,ValueError) else "实验文件不可读取。") from None

    @app.get("/diagnostics")
    def page(user=Depends(maintainer)):
        return FileResponse(Path(__file__).resolve().parent.parent / "static" / "diagnostics.html")

    @app.get("/api/lab/datasets")
    def datasets(user=Depends(maintainer)):
        def action():
            return [{key:value for key,value in lab().dataset_info(name).items() if key!="questions"}
                    for name in lab().datasets if lab().datasets[name].exists()]
        return checked(action)

    @app.get("/api/lab/datasets/{name}")
    def dataset(name:str,split:str="dev",user=Depends(maintainer)):
        if split not in {"dev","calibration","holdout","all"}:
            raise HTTPException(422,"题集分组无效。")
        return checked(lambda:lab().dataset_info(name,split))

    @app.post("/api/lab/datasets/{name}/reviews")
    def approve(name:str,body:DatasetReview,user=Depends(maintainer)):
        checked(lambda:lab().approve(name,body,user["username"]))
        return {"status":"approved"}

    @app.get("/api/lab/runs")
    def runs(user=Depends(maintainer)):
        return checked(lambda:[lab().report(r["id"],details=False) for r in lab().store.list()])

    @app.post("/api/lab/runs")
    def create(body:ExperimentConfig,user=Depends(maintainer)):
        result=checked(lambda:lab().create(body))
        lab().start()
        return result

    @app.get("/api/lab/runs/{run_id}")
    def report(run_id:str,user=Depends(maintainer)):
        return checked(lambda:lab().report(run_id))

    @app.post("/api/lab/runs/{run_id}/cancel")
    def cancel(run_id:str,user=Depends(maintainer)):
        checked(lambda:lab().store.cancel(run_id))
        return {"status":"cancel_requested","note":"已开始的请求结束后停止后续任务。"}

    @app.post("/api/lab/runs/{run_id}/resume")
    def resume(run_id:str,user=Depends(maintainer)):
        checked(lambda:lab().store.resume(run_id))
        lab().start()
        return {"status":"queued"}

    @app.post("/api/lab/runs/{run_id}/reviews")
    def review(run_id:str,body:ClaimReview,user=Depends(maintainer)):
        checked(lambda:lab().store.review(run_id,body.model_dump(),user["username"]))
        return {"status":"review_saved"}

    @app.get("/api/lab/compare")
    def compare(left:str,right:str,user=Depends(maintainer)):
        return checked(lambda:lab().compare(left,right))

    @app.get("/api/lab/runs/{run_id}/export")
    def export(run_id:str,user=Depends(maintainer)):
        result=checked(lambda:lab().report(run_id))
        return JSONResponse(result,headers={"Content-Disposition":f'attachment; filename="experiment-{result["id"]}.json"'})

    @app.post("/api/lab/import")
    def import_report(body:ImportRequest,user=Depends(maintainer)):
        return checked(lambda:lab().import_results(body))

    previous_lifespan=app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application) as state:
            try:
                yield state
            finally:
                if hasattr(application.state,"lab"):
                    application.state.lab.close()
    app.router.lifespan_context=lifespan
