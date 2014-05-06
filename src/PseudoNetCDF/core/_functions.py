from warnings import warn
import re
import numpy as np
from collections import defaultdict, OrderedDict


from _files import PseudoNetCDFFile
from _variables import PseudoNetCDFMaskedVariable, PseudoNetCDFVariable

def getvarpnc(f, varkeys, coordkeys = []):
    coordkeys = set(coordkeys)
    if varkeys is None:
        varkeys = list(set(f.variables.keys()).difference(coordkeys))
    else:
        newvarkeys = list(set(varkeys).intersection(f.variables.keys()))
        newvarkeys.sort()
        oldvarkeys = list(varkeys)
        oldvarkeys.sort()
        if newvarkeys != oldvarkeys:
            warn('Skipping %s' % ', '.join(set(oldvarkeys).difference(newvarkeys)))
        varkeys = newvarkeys

    outf = PseudoNetCDFFile()
    for propkey in f.ncattrs():
        setattr(outf, propkey, getattr(f, propkey))
    for varkey in varkeys:
        try:
            var = eval(varkey, None, f.variables)
        except:
            var = f.variables[varkey]
        for dimk, dimv in zip(var.dimensions, var.shape):
            if dimk not in outf.dimensions:
                newdimv = outf.createDimension(dimk, dimv)
                if f.dimensions[dimk].isunlimited():
                    newdimv.setunlimited(True)
                coordkeys.add(dimk)
                try:
                    tempv = f.variables[dimk]
                    if hasattr(tempv, 'bounds'):
                        coordkeys.add(tempv.bounds.strip())
                except (ValueError, KeyError, AttributeError), e:
                    pass
        for coordk in coordkeys:
            if coordk in f.dimensions and coordk not in outf.dimensions:
                newdimv = outf.createDimension(coordk, len(f.dimensions[coordk]))
                if f.dimensions[coordk].isunlimited():
                    newdimv.setunlimited(True)
    
        propd = dict([(k, getattr(var, k)) for k in var.ncattrs()])
        outf.createVariable(varkey, var.dtype.char, var.dimensions, values = var[...], **propd)
    for coordkey in coordkeys:
        if coordkey in f.variables.keys():
            coordvar = f.variables[coordkey]
            propd = dict([(k, getattr(coordvar, k)) for k in coordvar.ncattrs()])
            outf.createVariable(coordkey, coordvar.dtype.char, coordvar.dimensions, values = coordvar[...], **propd)
            for dk in coordvar.dimensions:
                if dk not in outf.dimensions:
                    dv = outf.createDimension(dk, len(f.dimensions[dk]))
                    dv.setunlimited(f.dimensions[dk].isunlimited())
    return outf


def interpvars(f, weights, dimension, loginterp = []):
    """
    f - PseudoNetCDFFile
    weights - weights for new dimensions from old dimension dim(new, old)
    dimension - which dimensions will be reduced
    loginterp - iterable of keys to interp on log scale
    """
    outf = PseudoNetCDFFile()
    outf.dimensions = f.dimensions.copy()
    if hasattr(f, 'groups'):
        for grpk, grpv in f.groups.items():
            outf.groups[grpk] = interpvars(grpv, weights, dimension)
    
    oldd = f.dimensions[dimension]
    didx, = [i for i, l in enumerate(weights.shape) if len(oldd) == l]
    
    newd = outf.createDimension(dimension, weights.shape[didx - 1])
    newd.setunlimited(oldd.isunlimited())
    for vark, oldvar in f.variables.iteritems():
        if dimension in oldvar.dimensions:
            dimidx = list(oldvar.dimensions).index(dimension)
            if hasattr(oldvar, '_FillValue'):
                kwds = dict(fill_value = oldvar._FillValue)
            else:
                kwds = dict()
            newvar = outf.createVariable(vark, oldvar.dtype.char, oldvar.dimensions, **kwds)
            for ak in oldvar.ncattrs():
                setattr(newvar, ak, getattr(oldvar, ak))
            if len(weights.shape) <= len(oldvar.dimensions):
                weightslice = (None,) * (dimidx) + (Ellipsis,) + (None,) * len(oldvar.dimensions[dimidx + 1:])
            else:
                weightslice = slice(None)        
            varslice = (slice(None,),) * dimidx + (None,)
            if vark in loginterp:
                logv = np.ma.exp((weights[weightslice] * np.ma.log(oldvar[varslice])).sum(dimidx + 1))
                newvar[:] = logv
            else:
                linv = (weights[weightslice] * oldvar[varslice]).sum(dimidx + 1)
                newvar[:] = linv
        else:
            outf.variables[vark] = oldvar
    return outf

def extract(f, lonlat, unique = False, gridded = None, method = 'nn'):
    from StringIO import StringIO
    outf = PseudoNetCDFFile()
    outf.dimensions = f.dimensions.copy()
    if hasattr(f, 'groups'):
        outf.groups = {}
        for grpk, grpv in f.groups.items():
            outf.groups[grpk] = extract(grpv, lonlat)
    
    longitude = f.variables['longitude'][:]
    latitude = f.variables['latitude'][:]
    if gridded is None:
        gridded = ('longitude' in f.dimensions and 'latitude' in f.dimensions) or \
                  ('COL' in f.dimensions and 'ROW' in f.dimensions) or \
                  ('x' in f.dimensions and 'y' in f.dimensions)
    outf.lonlatcoords = ('/'.join(lonlat))
    lons, lats = np.genfromtxt(StringIO(outf.lonlatcoords.replace('/', '\n')), delimiter = ',').T
    latlon1d = longitude.ndim == 1 and latitude.ndim == 1
    if method == 'nn':
        if latlon1d and gridded:
            latitude = latitude[(slice(None), None, None)]
            longitude = longitude[(None, slice(None), None)]
        else:
            latitude = latitude[Ellipsis, None]
            longitude = longitude[Ellipsis, None]
    
        lonlatdims = latitude.ndim - 1
        londists = longitude - lons[(None,) * lonlatdims]
        latdists = latitude - lats[(None,) * lonlatdims]
        totaldists = ((latdists**2 + londists**2)**.5)
        if latlon1d and not gridded:
            latidxs, = lonidxs, = np.unravel_index(totaldists.reshape(-1, latdists.shape[-1]).argmin(0), totaldists.shape[:-1])
        else:
            latidxs, lonidxs = np.unravel_index(totaldists.reshape(-1, latdists.shape[-1]).argmin(0), totaldists.shape[:-1])
        def extractfunc(v, thiscoords):
            newslice = tuple([{'latitude': latidxs, 'longitude': lonidxs, 'points': latidxs, 'PERIM': latidxs}.get(d, slice(None)) for d in thiscoords])
            return v[newslice]
    elif method == 'KDTree':
        if latlon1d and gridded:
            longitude, latitude = np.meshgrid(longitude, latitude)
        from scipy.spatial import KDTree
        tree = KDTree(np.ma.array([latitude.ravel(), longitude.ravel()]).T)
        dists, idxs = tree.query(np.ma.array([lats, lons]).T)
        if latlon1d and not gridded:
            latidxs, = lonidxs, = np.unravel_index(idxs, latitude.shape)
        else:
            latidxs, lonidxs = np.unravel_index(idxs, latitude.shape)
        def extractfunc(v, thiscoords):
            newslice = tuple([{'latitude': latidxs, 'longitude': lonidxs, 'points': latidxs, 'PERIM': latidxs}.get(d, slice(None)) for d in thiscoords])
            return v[newslice]
    elif method in ('linear', 'cubic', 'quintic'):
        from scipy.interpolate import interp2d
        if latlon1d and gridded:
            longitude, latitude = np.meshgrid(longitude, latitude)
        def extractfunc(v, thiscoords):
            i2df = interp2d(latitude, longitude, v, method = method)
            np.ma.array([i2df(lat, lon) for lat, lon in zip(lats, lons)])
    else:
        raise ValueError('method must be: nn, KDTree')
    if unique:
        tmpx = OrderedDict()
        for lon, lat, lonlatstr in zip(lonidxs, latidxs, outf.lonlatcoords.split('/')):
            if (lon, lat) not in tmpx:
                tmpx[(lon, lat)] = lonlatstr
        
        lonidxs, latidxs = np.array(tmpx.keys()).T
        outf.lonlatcoords_orig = outf.lonlatcoords
        outf.lonlatcoords = '/'.join([tmpx[k] for k in zip(lonidxs, latidxs)])
#     longitude = f.variables['longitude'][:]
#     latitude = f.variables['latitude'][:]
#     latidxs = []
#     lonidxs = []
#     for lon, lat in zip(lons, lats):
#         londist = lon - longitude
#         latdist = lat - latitude
#         totaldist = (latdist[:, None]**2 + londist[None, :]**2)**.5
#         latidxa, lonidxa = np.where(totaldist.min() == totaldist)
#         if len(latidxa) > 1:
#             warn("Selecting first of equidistant points")
#             
#         latidx = latidxa[0]
#         lonidx = lonidxa[0]
#         #lonidx = abs(londist).argmin()
#         #latidx = abs(latdist).argmin()
#         #import pdb; pdb.set_trace()
#         latidxs.append(latidx)
#         lonidxs.append(lonidx)
#     latidxs = array(latidxs)
#     lonidxs = array(lonidxs)
    for k, v in f.variables.items():
        try:
            coords = v.coordinates.split()
        except:
            coords = v.dimensions
        dims = v.dimensions
        outf.createDimension('points', len(latidxs))
        if 'longitude' in coords or 'latitude' in coords:
            try:
                del outf.variables[k]
            except:
                pass
            newdims = []
            if len(dims) != len(coords):
                thiscoords = dims
            else:
                thiscoords = coords
            for d, c in zip(dims, thiscoords):
                if d not in ('longitude', 'latitude') and c not in ('longitude', 'latitude'):
                    newdims.append(d)
                else:
                    if 'points' not in newdims:
                        newdims.append('points')
                        
            
            newdims = tuple(newdims)
            newv = extractfunc(v, thiscoords)
            
            nv = outf.createVariable(k, v.dtype.char, newdims, values = extractfunc(v, thiscoords))
            for ak in v.ncattrs():
                setattr(nv, ak, getattr(v, ak))
            setattr(nv, 'coordinates', getattr(v, 'coordinates', ' '.join(coords)))
            for di, dk in enumerate(newdims):
                if dk not in outf.dimensions:
                    outf.createDimension(dk, nv.shape[di])
    return outf
    
def mask_vals(f, maskdef, metakeys = 'time layer level latitude longitude time_bounds latitude_bounds longitude_bounds ROW COL LAY TFLAG ETFLAG'.split()):
    for varkey, var in f.variables.iteritems():
        if varkey not in metakeys:
            vout = eval('np.ma.masked_%s(var[:], %s)' % tuple(maskdef.split(',')))
            f.variables[varkey] = PseudoNetCDFMaskedVariable(f, varkey, var.dtype.char, var.dimensions, values = vout, **dict([(pk, getattr(var, pk)) for pk in var.ncattrs()]))
    return f
    
def slice_dim(f, slicedef, fuzzydim = True):
    """
    variables have dimensions (e.g., time, layer, lat, lon), which can be subset using 
        slice_dim(f, 'dim,start,stop,stride')
        
    e.g., slice_dim(f, 'layer,0,47,5') would sample every fifth layer starting at 0
    """
    historydef = "slice_dim(f, %s, fuzzydim = %s); " % (slicedef, fuzzydim)
    slicedef = slicedef.split(',')
    slicedef = [slicedef[0]] + map(eval, slicedef[1:])
    if len(slicedef) == 2:
        slicedef.append(slicedef[-1] + 1)
    slicedef = (slicedef + [None,])[:4]
    dimkey, dmin, dmax, dstride = slicedef    
    unlimited = f.dimensions[dimkey].isunlimited()
    if fuzzydim:
        partial_check = [key for key in f.dimensions if dimkey == key[:len(dimkey)] and key[len(dimkey):].isdigit()]
        for dimk in partial_check:
            f = slice_dim(f, '%s,%s,%s,%s' % (dimk, dmin, dmax, dstride))
        
    for varkey in f.variables.keys():
        var = f.variables[varkey]
        if dimkey not in var.dimensions:
            continue
        axis = list(var.dimensions).index(dimkey)
        vout = var[...].swapaxes(0, axis)[dmin:dmax:dstride].swapaxes(0, axis)
        
        newlen = vout.shape[axis]
        newdim = f.createDimension(dimkey, newlen)
        newdim.setunlimited(unlimited)
        f.variables[varkey] = vout
    history = getattr(f, 'history', '')
    history += historydef
    setattr(f, 'history', history)

    return f
    
def reduce_dim(f, reducedef, fuzzydim = True, metakeys = 'time layer level latitude longitude time_bounds latitude_bounds longitude_bounds ROW COL LAY TFLAG ETFLAG'.split()):
    """
    variable dimensions can be reduced using
    
    reduce_dim(file 'dim,function,weight')
    
    e.g., reduce_dim(layer,mean,weight).
    
    Weighting is not fully functional.
    """
    metakeys = [k for k in metakeys if k in f.variables.keys()]
    historydef = "reduce_dim(f, %s, fuzzydim = %s, metakeys = %s); " % (reducedef, fuzzydim, metakeys)
    import numpy as np
    commacount = reducedef.count(',')
    if commacount == 3:
        dimkey, func, numweightkey, denweightkey = reducedef.split(',')
        numweight = f.variables[numweightkey]
        denweight = f.variables[denweightkey]
    elif commacount == 2:
        dimkey, func, numweightkey = reducedef.split(',')
        numweight = f.variables[numweightkey]
        denweightkey = None
    elif commacount == 1:
        dimkey, func = reducedef.split(',')
        numweightkey = None
        denweightkey = None
    if fuzzydim:
        partial_check = [key for key in f.dimensions if dimkey == key[:len(dimkey)] and key[len(dimkey):].isdigit()]
        for dimk in partial_check:
            if commacount == 1:
                f = reduce_dim(f, '%s,%s' % (dimk, func),)
            elif commacount == 2:
                f = reduce_dim(f, '%s,%s,%s' % (dimk, func, numweightkey),)
            elif commacount == 3:
                f = reduce_dim(f, '%s,%s,%s,%s' % (dimk, func, numweightkey, denweightkey),)
    
    unlimited = f.dimensions[dimkey].isunlimited()
    f.createDimension(dimkey, 1)
    if unlimited:
        f.dimensions[dimkey].setunlimited(True)

    for varkey in f.variables.keys():
        var = f.variables[varkey]
        if dimkey not in var.dimensions:
            continue
        
        axis = list(var.dimensions).index(dimkey)
        def addunitydim(var):
            return var[(slice(None),) * (axis + 1) + (None,)]
        vreshape = addunitydim(var)
        if not varkey in metakeys:
            if numweightkey is None:
                vout = getattr(vreshape, func)(axis = axis)
            elif denweightkey is None:
                wvar = var * np.array(numweight, ndmin = var.ndim)[(slice(None),)*axis + (slice(0,var.shape[axis]),)]
                vout = getattr(wvar[(slice(None),) * (axis + 1) + (None,)], func)(axis = axis)
                vout.units = vout.units.strip() + ' * ' + numweight.units.strip()
                if hasattr(vout, 'base_units'):
                    vout.base_units = vout.base_units.strip() + ' * ' + numweight.base_units.strip()
            else:
                nwvar = var * np.array(numweight, ndmin = var.ndim)[(slice(None),)*axis + (slice(0,var.shape[axis]),)]
                vout = getattr(nwvar[(slice(None),) * (axis + 1) + (None,)], func)(axis = axis) / getattr(np.array(denweight, ndmin = var.ndim)[(slice(None),)*axis + (slice(0,var.shape[axis]), None)], func)(axis = axis)
        else:
            if '_bounds' not in varkey and '_bnds' not in varkey:
                vout = getattr(vreshape, func)(axis = axis)
            else:
                vout = getattr(vreshape, func)(axis = axis)
                vmin = getattr(vreshape, 'min')(axis = axis)
                vmax = getattr(vreshape, 'max')(axis = axis)
                if 'lon' in varkey:
                    vout[..., [0, 3]] = vmin[..., [0, 3]]
                    vout[..., [1, 2]] = vmin[..., [1, 2]]
                elif 'lat' in varkey:
                    nmin = vout.shape[-1] // 2
                    vout[..., :nmin] = vmin[..., :nmin]
                    vout[..., nmin:] = vmax[..., nmin:]
        nvar = f.variables[varkey] = PseudoNetCDFMaskedVariable(f, varkey, var.dtype.char, var.dimensions, values = vout)
        for k in var.ncattrs():
            setattr(nvar, k, getattr(var, k))

    history = getattr(f, 'history', '')
    history += historydef
    setattr(f, 'history', history)
    return f

def pncbo(op, ifile1, ifile2, coordkeys = [], verbose = False):
    """
    Perform binary operation (op) on all variables in ifile1
    and ifile2.  The returned file (rfile) contains the result
    
    rfile = ifile1 <op> ifile2
    
    op can be any valid operator (e.g., +, -, /, *, **, &, ||)
    """
    from PseudoNetCDF.sci_var import Pseudo2NetCDF
    
    # Copy infile1 to a temporary PseudoNetCDFFile
    p2p = Pseudo2NetCDF()
    p2p.verbose = verbose
    tmpfile = PseudoNetCDFFile()
    p2p.convert(ifile1, tmpfile)
    
    # For each variable, assign the new value
    # to the tmpfile variables.
    for k in tmpfile.variables.keys():
        if k in coordkeys: continue
        outvar = tmpfile.variables[k]
        in1var = ifile1.variables[k]
        if k not in ifile2.variables.keys():
            warn('%s not found in ifile2')
            continue
        in2var = ifile2.variables[k]
        if outvar.ndim > 0:
            outvar[:] = np.ma.masked_invalid(eval('in1var[:] %s in2var[:]' % op)).filled(-999)
        else:
            outvar.itemset(np.ma.masked_invalid(eval('in1var %s in2var' % op))).filled(-999)
        outvar.fill_value = -999
    return tmpfile

def _namemangler(k):
    k = k.replace('$', 'dollar')
    k = k.replace('-', 'hyphen')
    k = k.replace('(', 'lparen')
    k = k.replace(')', 'rparen')
    return k

def pncexpr(expr, ifile, verbose = False):
    """
    Evaluate an arbitrary expression in the context of ifile.variables
    and add the result to the file with appropriate units.
    """
    from PseudoNetCDF.sci_var import Pseudo2NetCDF
    
    # Copy file to temporary PseudoNetCDF file
    p2p = Pseudo2NetCDF()
    p2p.verbose = verbose
    tmpfile = PseudoNetCDFFile()
    p2p.convert(ifile, tmpfile)

    # Get NetCDF variables as a dictionary with 
    # names mangled to allow special characters
    # in the names
    vardict = dict([(_namemangler(k), ifile.variables[k]) for k in ifile.variables.keys()])
    vardict['np'] = np
    
    # Final all assignments in the expression
    # expr should allow for any valid expression
    assign_keys = re.findall(r'(?:^|;)\s*([a-zA-Z][a-zA-Z0-9_]*)\s*(?=[=])', expr, re.M)
    
    # Create temporary default dictionaries
    # and evaluate the expression
    # this results in identifying all used variables
    tmp3dict = defaultdict(lambda: 1, dict(np = np))
    tmp4dict = dict([(k, 1) for k in assign_keys])
    
    exec(expr, tmp4dict, tmp3dict)
    tmp3dict.pop('np')

    # Distinguish between used variables and new variables
    used_keys = [k_ for k_ in set(tmp3dict.keys()) if k_ in vardict]
    
    # Use the first used variable
    # to get properties and create all
    # new variables
    tmpvar = vardict[used_keys[0]]
    if hasattr(tmpvar, '_FillValue'):
        kwds = dict(fill_value = tmpvar._FillValue)
    else:
        kwds = {}
    for key in assign_keys:
        newvar = tmpfile.createVariable(key, tmpvar.dtype.char, tmpvar.dimensions, **kwds)
        for propk in tmpvar.ncattrs():
            setattr(newvar, propk, getattr(tmpvar, propk))
        
    # Use null slide to prevent reassignment of new variables.
    for assign_key in assign_keys:
        expr = re.sub(r'\b%s\b' % assign_key, '%s[:]' % assign_key, expr)
    
    # Add all used constants as properties
    # of the output file
    from scipy import constants
    for k in dir(constants):
        if k not in vardict:
            vardict[k] = getattr(constants, k)
    
    # Assign expression to new variable.
    exec(expr, tmpfile.variables, vardict)
    
    return tmpfile
    
def seqpncbo(ops, ifiles, coordkeys = []):
    for op in ops:
        ifile1, ifile2 = ifiles[:2]
        newfile = pncbo(op = op, ifile1 = ifile1, ifile2 = ifile2, coordkeys = coordkeys)
        del ifiles[:2]
        ifiles.insert(0, newfile)
    return ifiles

def mesh_dim(f, mesh_def):
    dimkey, meshfactor, aggfunc = mesh_def.split(',')
    meshfactor = float(meshfactor)
    spread=lambda a, n, axis: a.repeat(n, axis) * meshfactor
    try:
        aggfunc = eval(aggfunc)
    except:
        aggfunc = getattr(np, aggfunc)
    if meshfactor < 1.:
        oldres = int(1./meshfactor)
        assert(1./meshfactor == oldres)
        newres = 1
    elif meshfactor > 1.:
        newres = int(meshfactor)
        assert(meshfactor == newres)
        oldres = 1
    from PseudoNetCDF.MetaNetCDF import newresolution
    nrf = newresolution(f, dimension = dimkey, oldres = oldres, newres = newres, repeat_method = aggfunc, condense_method = aggfunc)
    f.dimensions[dimkey] = nrf.dimensions[dimkey]
    for k, v in f.variables.iteritems():
        if dimkey in v.dimensions:
            f.variables[k] = nrf.variables[k]
    return f

def add_attr(f, attr_def):
    att_nm, var_nm, mode, att_typ, att_val = attr_def.split(',')
    if var_nm == 'global':
        var = f
    else:
        var = f.variables[var_nm]
    
    if not (att_typ == 'c' and isinstance(att_val, (str, unicode))):
        att_val = np.array(att_val, dtype = att_typ)
        
    if mode in ('a',):
        att_val = np.append(getattr(var, att_nm, []), att_val)
    
    if mode in ('a', 'c', 'm', 'o'):
        setattr(var, att_nm, att_val)
    elif mode in ('d',):
        delattr(var, att_nm)
    else:
        raise KeyError('mode must be either a c m o or d')
        setattr(var, att_nm, np.dtype(att_typ)(att_val))

def convolve_dim(f, convolve_def):
    convolve_parts = convolve_def.split(',')
    dimkey = convolve_parts.pop(0)
    mode = convolve_parts.pop(0)
    weights = np.array(convolve_parts, dtype = 'f')
    outf = PseudoNetCDFFile()
    from PseudoNetCDF.pncgen import Pseudo2NetCDF
    p2p = Pseudo2NetCDF(verbose = False)
    p2p.addGlobalProperties(f, outf)
    p2p.addDimensions(f, outf)
    dim = outf.dimensions[dimkey]
    dim = outf.createDimension(dimkey, len(np.convolve(weights, np.arange(len(dim)), mode = mode)))
    dim.setunlimited(f.dimensions[dimkey].isunlimited())
    for vark, var in f.variables.iteritems():
        lconvolve = dimkey in var.dimensions
        p2p.addVariable(f, outf, vark, data = not lconvolve)
        if lconvolve:
            axisi = list(var.dimensions).index(dimkey)
            values = np.apply_along_axis(func1d = lambda x_: np.convolve(weights, x_, mode = mode), axis = axisi, arr = var[:])
            outf.variables[vark][:] = values
    return outf

def stack_files(fs, stackdim):
    """
    Create files with dimensions extended by stacking.
    
    Currently, there is no sanity check...
    
    """
    f = PseudoNetCDFFile()
    tmpf = fs[0]
    dimensions = [f_.dimensions for f_ in fs]
    shareddims = {}
    for dimk, dim in tmpf.dimensions.items():
        if dimk == stackdim:
            continue
        dimlens = map(len, [dims[dimk] for dims in dimensions])
        if all([len(dim) == i for i in dimlens]):
            shareddims[dimk] = len(dim)
    differentdims = [set(dims.keys()).difference(shareddims.keys()) for dims in dimensions]
    assert(all([different == set([stackdim]) for different in differentdims]))
    from PseudoNetCDF.sci_var import Pseudo2NetCDF
    p2p = Pseudo2NetCDF(verbose = False)
    p2p.addDimensions(tmpf, f)
    f.createDimension(stackdim, sum([len(dims[stackdim]) for dims in dimensions]))
    p2p.addGlobalProperties(tmpf, f)
    for varkey, var in tmpf.variables.iteritems():
        if not stackdim in var.dimensions:
            p2p.addVariable(tmpf, f, varkey, data = True)
        else:
            axisi = list(var.dimensions).index(stackdim)
            values = np.ma.concatenate([f_.variables[varkey][:] for f_ in fs], axis = axisi)
            p2p.addVariable(tmpf, f, varkey, data = False)
            f.variables[varkey][:] = values
        
    return f