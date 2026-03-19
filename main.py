from datetime import datetime

from fastapi.exceptions import HTTPException

from config import host,user,password, db_name

from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel,ValidationError
import psycopg2 as psy
from psycopg2 import sql

app = FastAPI()

item = 1
machine_dict = [
    {
       'id':1,
        'size':'1250*1500*1500',
        'max_spin':9000,
        'move_table':False,
        'name':2

    },

]


# -----------модели--------------------
class Machine(BaseModel):
    size_x: int
    size_y: int
    size_z: int
    max_spin: int
    move_table: bool
    name: str
class PC(BaseModel):
    name: str
    program: str
    specs: str
class UP(BaseModel):
    code: str
    type_detail: int
    date: datetime
    developer: int
    machine: int
class Developers(BaseModel):
    pass
class Drawing(BaseModel):
    pass
class LicenseModel(BaseModel):
    pass
class Machine_dict(BaseModel):
    pass
class Maps(BaseModel):
    pass
class Type_detail_dict(BaseModel):
    pass

dict_table_names = {'Machines':Machine,
                    'PC':PC,
                    'UP':UP,
                    'developers':Developers,
                    'drawings':Drawing,
                    'license':LicenseModel,
                    'machine_dict':Machine_dict,
                    'maps':Maps,
                    'type_detail_dict':Type_detail_dict
                    }


# ----------GET методы---------------------
@app.get('/{name_table}',summary="получить данные таблицы полность",tags=["Основные методы CRUD"])
def get_all_item(name_table: str):
    if name_table not in dict_table_names.keys():
        raise HTTPException(
            status_code=404,
            detail=f"Таблицы '{name_table}' нет. Доступны: {dict_table_names.keys()}"
        )
    connection = psy.connect(
        host=host,
        user=user,
        password=password,
        database=db_name
    )
    try:

        with connection.cursor() as cursor:
            query = sql.SQL(
                '''
                SELECT * FROM {}
                '''
            ).format(sql.Identifier(name_table))
            cursor.execute(query)
            result = cursor.fetchall()
            return result
    finally:
        connection.close()

@app.get('/{name_table}/{id}',summary="получить строку",tags=["Основные методы CRUD"])
def get_one_item(name_table: str,id: int):
    if name_table not in dict_table_names.keys():
        raise HTTPException(
            status_code=404,
            detail=f"Таблицы '{name_table}' нет. Доступны: {dict_table_names.keys()}"
        )

    connection = psy.connect(
        host=host,
        user=user,
        password=password,
        database=db_name
    )
    try:
        with connection.cursor() as cursor:
            query = sql.SQL(
                '''
                SELECT * FROM {}
                WHERE id = %s
                '''
            ).format(sql.Identifier(name_table))
            cursor.execute(query,(id,))
            result = cursor.fetchone()
        return result
    finally:
        connection.close()
# ----------------POST методы------------------
@app.post("/{name_table}",summary="создать строку",tags=["Основные методы CRUD"])
def create_row(data:dict ,name_table: str):

    if name_table not in dict_table_names.keys():
        raise HTTPException(
            status_code=404,
            detail=f"Таблицы '{name_table}' нет. Доступны: {dict_table_names.keys()}"
        )
    try:

        print(data)
        model = dict_table_names[name_table]
        valid_data = model.model_validate(data)
        print(valid_data)
    except ValidationError as e:
         raise HTTPException(status_code=422, detail=e.errors())
    connection = psy.connect(
        host=host,
        user=user,
        password=password,
        database=db_name
    )
    try:
       fields = tuple(data.keys())
       values = tuple(data.values())
       print(values)


       query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *;").format(
           sql.Identifier(name_table),
                                      sql.SQL(', ').join(map(sql.Identifier,fields)),
                                        sql.SQL(', ').join([sql.Placeholder()] * len(data))
                                      )
       with connection.cursor() as cursor:
           cursor.execute(query,values )
           inserted = cursor.fetchone()  # получаем вставленную строку
           connection.commit()
       print(inserted)
       return "ALL DONE"
    finally:
        connection.close()


if __name__ == "__main__":
    uvicorn.run("main:app",reload=True)