"""Hulpproces voor zware modelverwerking (thumbnails, 3MF-info, plaatafmetingen, viewer).
Draait los van de webserver met een geheugenlimiet (THUMB_MEM_MB), zodat één enorm model nooit de hele server of
container laat vollopen. Protocol: opdrachten en antwoorden als pickle op stdin/stdout, voorafgegaan door 8 bytes lengte."""
import os, pickle, struct, sys


def main():
    mb = int(os.environ.get('THUMB_MEM_MB', '4096') or 0)
    if mb > 0:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (mb << 20, mb << 20))
        except Exception:  # Windows: geen resource-module
            pass
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    sys.stdout = sys.stderr  # losse print()s mogen het protocol niet verstoren
    import render
    while True:
        head = inp.read(8)
        if len(head) < 8:
            return
        fn, args, kw = pickle.loads(inp.read(struct.unpack('>Q', head)[0]))
        try:
            if fn == 'mesh_stl':
                V, F = render.load_mesh(*args, **kw)
                msg = ('ok', render.stl_bytes(V, F))
            else:
                msg = ('ok', getattr(render, fn)(*args, **kw))
        except BaseException as e:  # ook MemoryError
            try:
                pickle.dumps(e)
            except Exception:
                e = RuntimeError(f'{type(e).__name__}: {e}')
            msg = ('exc', e)
        V = F = None
        data = pickle.dumps(msg, protocol=4)
        out.write(struct.pack('>Q', len(data)) + data)
        out.flush()


if __name__ == '__main__':
    main()
