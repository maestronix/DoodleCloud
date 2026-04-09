from storage_core.cachefs import CachedMetadataStore
from storage_core.models import ChunkMetadata, FileMetadata
from tests.fakes import InMemoryMetadataStore


def test_warm_load_and_chunk_lookup():
    backing = InMemoryMetadataStore()
    file_meta = FileMetadata(
        file_id="f1",
        path="/movies/a.mp4",
        filename="a.mp4",
        size=100,
        mtime=10,
        ctime=10,
        content_type="video/mp4",
        checksum="abc",
        chunk_count=2,
    )
    backing.upsert_file(file_meta)
    backing.replace_chunks(
        "f1",
        [
            ChunkMetadata("f1", 0, 0, 60, "r0", None),
            ChunkMetadata("f1", 1, 60, 40, "r1", None),
        ],
    )

    cachefs = CachedMetadataStore(backing)
    cachefs.warm_load()

    assert cachefs.get_file_by_path("/movies/a.mp4").file_id == "f1"
    assert [c.remote_id for c in cachefs.get_chunks("f1")] == ["r0", "r1"]


def test_directory_projection_and_delete():
    backing = InMemoryMetadataStore()
    for idx, path in enumerate(["/media/show/ep1.mkv", "/media/show/ep2.mkv", "/media/movie.mkv"]):
        backing.upsert_file(
            FileMetadata(
                file_id=f"f{idx}",
                path=path,
                filename=path.split("/")[-1],
                size=50,
                mtime=10 + idx,
                ctime=10,
                content_type="video/x-matroska",
                checksum=None,
                chunk_count=1,
            )
        )

    cachefs = CachedMetadataStore(backing)
    cachefs.warm_load()

    root_entries = cachefs.list_directory_entries("/")
    assert any(e.path == "/media" and e.is_dir for e in root_entries)

    show_entries = cachefs.list_directory_entries("/media/show")
    assert len([e for e in show_entries if not e.is_dir]) == 2

    assert cachefs.delete_file_by_path("/media/movie.mkv")
    assert cachefs.get_file_by_path("/media/movie.mkv") is None
