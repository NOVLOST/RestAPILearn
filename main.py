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
    name: str
    work_PC:int
class Drawing(BaseModel):
    type_detail: int
    developer: int
    code: str
    version: int
    file: str
class LicenseModel(BaseModel):
    program: str
    key:str
    PC:int
class Machine_dict(BaseModel):
    name:str
class Maps(BaseModel):
    code:str
    date:str
    file:str
    developer:int
class Type_detail_dict(BaseModel):
    name:str

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
def patch_pattern_maker(name_table,data,id):

    fields = [ sql.SQL(' {} = %s').format(sql.Identifier(key)) for key in data.keys() ]
    values = tuple(list(data.values()) + [id])
    pattern = sql.SQL(' UPDATE {} SET {} WHERE id = %s RETURNING *').format(sql.Identifier(name_table),
                                                                            sql.SQL(', ').join(fields))
    return pattern,values

def valid_model_checker(name_table,data):
    try:
        model = dict_table_names[name_table]
        valid_data = model.model_validate(data)
    except ValidationError as e:
         raise HTTPException(status_code=422, detail=e.errors())

def exist_table_checker(name_table):
    if name_table not in dict_table_names.keys():
        raise HTTPException(
            status_code=404,
            detail=f"Таблицы '{name_table}' нет. Доступны: {dict_table_names.keys()}"
        )

def pattern_maker(name_table,flag_mode):
    if flag_mode:
        if name_table == "Machines": addition = ' WHERE m.id = %s'
        elif name_table == "UP": addition = ' WHERE UP.id = %s'
        elif name_table == "developers": addition = ' WHERE d.id = %s'
        elif name_table == "license": addition = ' WHERE l.id = %s'
        elif name_table == "maps": addition = ' WHERE m.id = %s'
        elif name_table == "drawings": addition = ' WHERE dr.id = %s'
        else:
            addition = ' WHERE id = %s'
    else:
        addition = ''
    if name_table == "Machines":
        pattern = ('SELECT m.id,m.size,m.max_spin,m.move_table,md.name FROM {} m '
                   ' INNER JOIN machine_dict md ON m.name = md.id' + addition)
    elif name_table == "UP":
        pattern = ('SELECT UP.id,UP.code,t.name,UP.date,d.name,md.name FROM {} UP '
                   ' INNER JOIN type_detail_dict t ON UP.type_detail = t.id'
                   ' INNER JOIN developers d ON UP.developer = d.id'
                   ' INNER JOIN machine_dict md ON UP.machine = md.id' + addition)
    elif name_table == "developers":
        pattern = ('SELECT d.id,d.name,p.name FROM {} d '
                   ' INNER JOIN "PC" p ON d."work_PC" = p.id  '+ addition)
    elif name_table == "license":
        pattern = ('SELECT l.id,l.program,l.key,p.name FROM {} l '
                   ' INNER JOIN "PC" p ON l."PC" = p.id  '+ addition)
    elif name_table == "maps":
        pattern = ("SELECT m.id,m.code,m.date,d.name,encode(m.file, 'base64' ) as key_base64  FROM {} m"
                   " INNER JOIN developers d ON d.id = m.developer  "+ addition)
    elif name_table == "drawings":
        pattern = ("SELECT dr.id,t.name,d.name,dr.code,dr.version,encode(dr.file, 'base64' ) as key_base64 FROM {} dr"
                   " INNER JOIN developers d ON d.id = dr.developer  "
                   " INNER JOIN type_detail_dict t ON t.id = dr.type_detail"+  addition)
    else:
        pattern = 'SELECT * FROM {} ' + addition
    return pattern

# ----------GET методы---------------------
@app.get('/{name_table}',summary="получить данные таблицы полность",tags=["Основные методы CRUD"])
def get_all_item(name_table: str):
    exist_table_checker(name_table)
    connection = psy.connect(
        host=host,
        user=user,
        password=password,
        database=db_name
    )
    try:

        with connection.cursor() as cursor:
            pattern = pattern_maker(name_table,flag_mode=False)
            query = sql.SQL(
               f'''
                {pattern}
                '''
            ).format(sql.Identifier(name_table))
            cursor.execute(query)
            result = cursor.fetchall()
            return result
    finally:
        connection.close()

@app.get('/{name_table}/{id}',summary="получить строку",tags=["Основные методы CRUD"])
def get_one_item(name_table: str,id: int):
    exist_table_checker(name_table)

    connection = psy.connect(
        host=host,
        user=user,
        password=password,
        database=db_name
    )
    try:
        with connection.cursor() as cursor:
            pattern = pattern_maker(name_table,flag_mode=True)
            query = sql.SQL(
                f'''
                {pattern}
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
    exist_table_checker(name_table)
    valid_model_checker(name_table, data)

    connection = psy.connect(
        host=host,
        user=user,
        password=password,
        database=db_name
    )
    try:
       fields = tuple(data.keys())
       values = tuple(data.values())

       query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *;").format(
           sql.Identifier(name_table),
                                      sql.SQL(', ').join(map(sql.Identifier,fields)),
                                        sql.SQL(', ').join([sql.Placeholder()] * len(data))
                                      )
       with connection.cursor() as cursor:
           cursor.execute(query,values )
           inserted = cursor.fetchone()  # получаем вставленную строку
           connection.commit()

       return f"ALL DONE {inserted} WRITE AND SAVE"
    finally:
        connection.close()

@app.delete("/{name_table}/{id}",summary="удалить строку",tags=["Основные методы CRUD"])
def row_deleter(name_table:str, id:int ):
    exist_table_checker(name_table)
    connection = psy.connect(
        host=host,
        user=user,
        password=password,
        database=db_name
    )
    try:

        query = sql.SQL(" DELETE FROM {} WHERE id = %s RETURNING *;").format(sql.Identifier(name_table) )
        with connection.cursor() as cursor:
            cursor.execute(query, (id,))
            inserted = cursor.fetchone()  # получаем вставленную строку
            connection.commit()
            return f' SUCCESSFULLY DELETED ROW {inserted}'
    finally:
        connection.close()

@app.patch("/{name_table}/{id}",summary="обновить строку",tags=["Основные методы CRUD"])
def row_updater(name_table:str,id:int,data:dict):
    exist_table_checker(name_table)
    valid_model_checker(name_table, data)
    connection = psy.connect(
        host=host,
        user=user,
        password=password,
        database=db_name
    )
    try:
        pattern,values = patch_pattern_maker(name_table,data,id)
        with connection.cursor() as cursor:
            cursor.execute(pattern, values)
            inserted = cursor.fetchone()  # получаем вставленную строку
            connection.commit()
            return f' SUCCESSFULLY UPDATED ROW {inserted}'
    finally:
        connection.close()


if __name__ == "__main__":
    uvicorn.run("main:app",reload=True)