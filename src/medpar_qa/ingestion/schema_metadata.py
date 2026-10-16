"""Read nested Parquet field names/types without materializing data rows."""
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=256)
def _read(path,size,modified):
    import pyarrow as pa
    import pyarrow.parquet as pq
    output=[]
    def visit(field,parent='$'):
        current=parent+'.'+field.name
        output.append({'name':field.name,'path':current,'type':str(field.type)})
        if pa.types.is_struct(field.type):
            for child in field.type:visit(child,current)
        elif pa.types.is_list(field.type) or pa.types.is_large_list(field.type):
            child=field.type.value_field
            if pa.types.is_struct(child.type):
                for nested in child.type:visit(nested,current+'[]')
    for field in pq.ParquetFile(path).schema_arrow:visit(field)
    return tuple(output)


def parquet_schema(path):
    p=Path(path);stat=p.stat()
    return list(_read(str(p.resolve()),stat.st_size,stat.st_mtime_ns))
