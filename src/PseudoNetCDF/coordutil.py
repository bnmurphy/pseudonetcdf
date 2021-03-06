from __future__ import print_function
from PseudoNetCDF import warn
import numpy as np
from collections import OrderedDict

def getlonlatcoordstr(ifile, makemesh = None):
    """
    ifile - file with latitude and longitude variables
    makemesh - use numpy.meshgrid to construct gridded values (default None)
               None - check if longitude and latitude are coordinate variables
                      or have different dimensions if so set to True
               True - use meshgrid
               False - assume latitude and longitude are on same g
    """
    lon = ifile.variables['longitude']
    lat = ifile.variables['latitude']
    
    if lon.dimensions != lat.dimensions or (lon.dimensions == ('longitude',) and lat.dimensions == ('latitude',)):
        lon, lat = np.meshgrid(lon[:], lat[:])
    
    
    return '/'.join(['%s,%s' % ll for ll in zip(lon[:].flat, lat[:].flat)])

def _parse_ref_date(base):
    from datetime import datetime
    fmts = [
            (lambda x: x.count(':') == 2 and x[-3:] == 'UTC', '+0000', '%Y-%m-%d %H:%M:%S UTC%z'), # has time and Z
            (lambda x: x.count(':') == 1 and x[-3:] == 'UTC', '+0000', '%Y-%m-%d %H:%M UTC%z'), # has time and Z
            (lambda x: 'UTC' in x, '+0000', '%Y-%m-%d %H UTC%z'), # has hour and Z
            (lambda x: x.count(':') == 2 and x[-1] == 'Z', '', '%Y-%m-%d %H:%M:%SZ'), # has time and Z
            (lambda x: x.count(':') == 1 and x[-1] == 'Z', '', '%Y-%m-%d %H:%MZ'), # has time and Z
            (lambda x: 'Z' == x[-1], '+0000', '%Y-%m-%d %HZ%z'), # has hour and Z
            (None, '', '%Y-%m-%d %H:%M:%S%z'), # full ISO8601 datetime with numeric timezone info
            (None, '+0000', '%Y-%m-%d %H:%M:%S%z'), # missing timezone
            (None, ':00+0000', '%Y-%m-%d %H:%M:%S%z'), # missing seconds and timezone
            (None, '', '%Y-%m-%d %H:%M%z'), # missing seconds
            (None, ':00:00+0000', '%Y-%m-%d %H:%M:%S%z'), # missing minutes and seconds and timezone
            (None, '', '%Y-%m-%d %H%z'), # missing minutes and seconds
            (None, ' 00:00:00+0000', '%Y-%m-%d %H:%M:%S%z'), # missing time and timezone
            (None, '', '%Y-%m-%d %z'), # missing time
            (None, '', '%Y-%m-%d%z'), # missing time
           ]
    for test, suffix, fmt in fmts:
        if test is None or test(base):
            try:
                rdate = datetime.strptime(base + suffix, fmt)
                return rdate
            except Exception as e:
                pass
    else:
        #try using netcdftime
        try:
            import netcdftime
            ut = netcdftime.netcdftime.utime(time.units.strip())
            sdate = ut.num2date(0.)
            return sdate
        except Exception as e:
            raise ValueError('Could not find appropriate date; tried and failed to use netcdftime' + str(e))

def gettimes(ifile):
    from datetime import datetime, timedelta
    if 'time' in ifile.variables.keys():
        time = ifile.variables['time']
        if 'since' in time.units:
            unit, base = time.units.strip().split(' since ')
            sdate = _parse_ref_date(base)
            out = sdate + np.array([timedelta(**{unit: float(i)}) for i in time[:]])
            return out
        else:
            return time
    elif 'TFLAG' in ifile.variables.keys():
        dates = ifile.variables['TFLAG'][:][:, 0, 0]
        times = ifile.variables['TFLAG'][:][:, 0, 1]
        yyyys = (dates // 1000).astype('i')
        jjj = dates % 1000
        hours = times // 10000
        minutes = times % 10000 // 100
        seconds = times % 100
        days = jjj + (hours + minutes / 60. + seconds / 3600.) / 24.
        out = np.array([datetime(yyyy, 1, 1) + timedelta(days = day - 1) for yyyy, day in zip(yyyys, days)])
        return out
    elif 'tau0' in ifile.variables.keys():
        out = datetime(1985, 1, 1, 0) + np.array([timedelta(hours =i) for i in ifile.variables['tau0'][:]])
        return out
    else:
        raise ValueError('cannot understand time for file')

def gettimebnds(ifile):
    from datetime import datetime, timedelta
    if 'TFLAG' in ifile.variables.keys():
        dates = ifile.variables['TFLAG'][:][:, 0, 0]
        times = ifile.variables['TFLAG'][:][:, 0, 0]
        yyyys = (dates // 1000).astype('i')
        jjj = dates % 1000
        hours = times // 10000
        minutes = times % 10000 // 100
        seconds = times % 100
        days = jjj + (hours + minutes / 60. + seconds / 3600.) / 24.
        out = np.array([datetime(yyyy, 1, 1) + timedelta(days = day - 1) for yyyy, day in zip(yyyys, days)])
        
        hours = ifile.TSTEP // 10000
        minutes = ifile.TSTEP % 10000 // 100
        seconds = ifile.TSTEP % 100
        hours = (hours + minutes / 60. + seconds / 3600.)
        return np.array([out, out + timedelta(hours = hours)]).T
    elif 'tau0' in ifile.variables.keys() and 'tau1' in ifile.variables.keys():
        out1 = datetime(1985, 1, 1, 0) + np.array([timedelta(hours =i) for i in ifile.variables['tau0'][:]])
        out2 = datetime(1985, 1, 1, 0) + np.array([timedelta(hours =i) for i in ifile.variables['tau1'][:]])
        return np.array([out1, out2]).T
    elif 'time' in ifile.variables.keys():
        time = ifile.variables['time']
        if 'since' in time.units:
            unit, base = time.units.strip().split(' since ')
            sdate = _parse_ref_date(base)
            out = sdate + np.array([timedelta(**{unit: float(i)}) for i in time[:]])
            if len(out) > 1:
                dt = (out[1] - out[0])
            else:
                dt = timedelta(**{unit: 0.})
            
            return np.array([out, out + dt]).T
        else:
            return np.array([time, time + (time[1] - time[0])]).T
    else:
        raise ValueError('cannot understand time for file')

def getsigmabnds(ifile):
    if hasattr(ifile, 'VGLVLS'):
        return ifile.VGLVLS[:]
    elif 'etai_pressure' in ifile.variables:
        etai_pressure = ifile.variables['etai_pressure']
        return (etai_pressure - etai_pressure[-1]) / (etai_pressure[0] - etai_pressure[-1])
    elif 'layer_bounds' in ifile.variables:
        lay = ifile.variables['layer_bounds']
        if lay.units.strip() in ('Pa', 'hPa'):
            sigma = (lay[:] -lay[-1]) / (lay[0] - lay[-1])
            return sigma
        else:
            warn("Unknown tranform of layer to sigma; sigma units %s" % lay.units)
            return lay
    else:
        warn("Unknown vertical coordinate")
        if hasattr(ifile, 'NLAYS'):
            nlays = ifile.NLAYS
        elif 'LAY' in ifile.dimensions:
            nlays = len(ifile.dimensions['LAY'])
        elif 'lev' in ifile.dimensions:
            nlays = len(ifile.dimensions['lev'])
        elif 'layer' in ifile.dimensions:
            nlays = len(ifile.dimensions['layer'])
        else:
            nlays = 1
        return np.arange(nlays)
        
def pres_from_sigma(sigma, pref, ptop, avg = False):
    pres = sigma * (pref - ptop) + ptop
    if avg:
        pres = pres[:-1] + np.diff(pres) / 2.
    return pres

def getpresmid(ifile, pref = 101325., ptop = None):
    presb = getpresbnds(ifile, pref = 101325., ptop = None)
    return presb[:-1] + np.diff(presb) / 2

def getsigmamid(ifile):
    sigmab = getsigmabnds(ifile)
    return sigmab[:-1] + np.diff(sigmab) / 2

def getpresbnds(ifile, pref = 101325., ptop = None):
    if 'etai_pressure' in ifile.variables:
        return ifile.variables['etai_pressure'][:]
    elif 'layer_bounds' in ifile.variables:
        return ifile.variables['layer_bounds'][:]
    else:
        sigma = getsigmabnds(ifile)
        if ptop is None:
            if hasattr(ifile, 'VGTOP'):
                ptop = ifile.VGTOP
            else:
                warn("Assuming VGTOP = 10000 Pa")
                ptop = 10000
            
        return pres_from_sigma(sigma, pref = pref, ptop = ptop)

def getlatbnds(ifile):
    if 'latitude_bounds' in ifile.variables:
        latb = ifile.variables['latitude_bounds']
        unit = latb.units.strip()
        if 'nv' in latb.dimensions:
            if latb[:].ndim == 2 and len(ifile.dimensions['nv']) == 2:
                latb = np.append(latb[:][:, 0], latb[:][-1, 1])
            elif latb[:].ndim == 2 and len(ifile.dimensions['nv']) == 4:
                latb = np.append(latb[:][:, 0], latb[:][-1, 1])
            elif latb.ndim == 3:
                latb = latb[:, :, 0]
            
    elif 'latitude' in ifile.variables:
        latb = ifile.variables['latitude']
        unit = latb.units.strip()
        latb = latb[:]
        latdiff = np.diff(latb, axis = 0)
        if not (latdiff == latdiff[[0]]).all():
            warn('Latitude bounds are approximate')
        latb = np.apply_along_axis(np.convolve, 0, latb, [0.5, 0.5])
        latb[0] *= 2
        latb[-1] *= 2
        #latb = np.concatenate([latb, latb[[-1]]], axis = 0) - .5 * np.concatenate([latdiff[:], latdiff[[-1]], -latdiff[[-1]]], axis = 0)
        #latb = np.minimum(90, latb)
        #latb = np.maximum(-90, latb)
        if latb.ndim == 2:
            latb = np.append(latb, latb[:, [-1]], axis = 1)
            
    elif 'ROW' in ifile.dimensions:
        unit = 'x (m)'
        latb = np.arange(len(ifile.dimensions['ROW']) + 1) * getattr(ifile, 'YCELL', 1) / 1000.
    else:
        raise KeyError('latitude bounds not found')
    return latb, unit

def getybnds(ifile):
    if 'ROW' in ifile.dimensions:
        unit = 'y (m)'
        latb = np.arange(len(ifile.dimensions['ROW']) + 1) * getattr(ifile, 'YCELL', 1)
    elif 'south_north' in ifile.dimensions:
        unit = 'y (m)'
        lonb = np.arange(len(ifile.dimensions['south_north']) + 1) * getattr(ifile, 'DY', 1)
    else:
        raise KeyError('latitude bounds not found')
    return latb, unit

def getlonbnds(ifile):
    if 'longitude_bounds' in ifile.variables:
        lonb = ifile.variables['longitude_bounds']
        unit = lonb.units.strip()
        if 'nv' in lonb.dimensions:
            if lonb[:].ndim == 2 and len(ifile.dimensions['nv']) == 2:
                lonb = np.append(lonb[:][:, 0], lonb[:][-1, 1])
            elif lonb[:].ndim == 3:
                lonb = lonb[:][:, :, 0]
    elif 'longitude' in ifile.variables:
        lonb = ifile.variables['longitude']
        unit = lonb.units.strip()
        lonb = lonb[:]
        if lonb.ndim > 1:
            londiff = np.diff(lonb, axis = 1)
            alldiffsame = (londiff == londiff[:, [0]]).all()
        elif lonb.ndim == 1:
            alldiffsame = True
            londiff = np.diff(lonb)
        else:
            raise ValueError("Cannot infer longitude bounds when dimensions >2")
        if not alldiffsame:
            londiff = np.diff(lonb, axis = 1)
            if not (londiff == londiff[:, [0]]).all():
                warn('Longitude bounds are approximate')
            lonb = np.concatenate([lonb, lonb[:, [-1]]], axis = 1) - .5 * np.concatenate([londiff[:, :], londiff[:, [-1]], -londiff[:, [-1]]], axis = 1)
            lonb = np.append(lonb, lonb[[-1], :], axis = 0)
        else:
            londiff = np.diff(lonb, axis = 0)
            lonb = np.concatenate([lonb, lonb[[-1]]], axis = 0) - .5 * np.concatenate([londiff[:], londiff[[-1]], -londiff[[-1]]], axis = 0)

    else:
        raise KeyError('longitude bounds not found')
    return lonb, unit

def getxbnds(ifile):
    if 'COL' in ifile.dimensions:
        unit = 'x (m)'
        lonb = np.arange(len(ifile.dimensions['COL']) + 1) * getattr(ifile, 'XCELL', 1)
    elif 'west_east' in ifile.dimensions:
        unit = 'x (m)'
        lonb = np.arange(len(ifile.dimensions['west_east']) + 1) * getattr(ifile, 'DX', 1)
    else:
        raise KeyError('x bounds not found')
    return lonb, unit

def getcdo(ifile):
    """
    ifile - file containing latitude, longitude and optionally latitude_bounds and longitude_bounds
    """
    import textwrap
    def wrapper(first, instr):
        outstr = "\n".join(textwrap.wrap(instr, width = 72, subsequent_indent = ' '*12, initial_indent = first))
        return outstr
    
    outdict = {}
    if 'latitude' in ifile.dimensions and 'longitude' in ifile.dimensions:
        outdict['gridtype'] = 'lonlat'
        outdict['nverts'] = 2
        outdict['NCOLS'] = len(ifile.dimensions['longitude'])
        outdict['NROWS'] = len(ifile.dimensions['latitude'])
    elif 'ROW' in ifile.dimensions and 'COL' in ifile.dimensions:
        outdict['gridtype'] = 'curvilinear'
        outdict['nverts'] = 4
        outdict['NCOLS'] = len(ifile.dimensions['COL'])
        outdict['NROWS'] = len(ifile.dimensions['ROW'])
    elif 'south_north' in ifile.dimensions and 'west_east' in ifile.dimensions:
        outdict['gridtype'] = 'curvilinear'
        outdict['nverts'] = 4
        outdict['NCOLS'] = len(ifile.dimensions['west_east'])
        outdict['NROWS'] = len(ifile.dimensions['south_north'])
    else:
        raise ValueError('Could not find latitude/longitude or ROW/COL')
    outdict['NCELLS'] = outdict['NCOLS'] * outdict['NROWS']
    LONSTR = ' '.join(' '.join(['%f' % lon for lon in row]) for row in ifile.variables['longitude'][:])
    LATSTR = ' '.join(' '.join(['%f' % lat for lat in row]) for row in ifile.variables['latitude'][:])
    LONBSTR = ' '.join(' '.join([' '.join(['%f' % lon for lon in cell]) for cell in row]) for row in ifile.variables['longitude_bounds'][:])
    LATBSTR = ' '.join(' '.join([' '.join(['%f' % lat for lat in cell]) for cell in row]) for row in ifile.variables['latitude_bounds'][:])
    outdict['LONSTR'] = wrapper('xvals     = ', LONSTR)
    outdict['LONBSTR'] = wrapper('xbounds   = ', LONBSTR)
    outdict['LATSTR'] = wrapper('yvals     = ', LATSTR)
    outdict['LATBSTR'] = wrapper('ybounds   = ', LATBSTR)
    return """
    gridtype  = curvilinear
    nvertex   = %(nverts)d
    gridsize  = %(NCELLS)d
    xsize     = %(NCOLS)d
    ysize     = %(NROWS)d
    xunits    = degrees_east
    yunits    = degrees_north
    %(LONSTR)s
    %(LONBSTR)s
    %(LATSTR)s
    %(LATBSTR)s
    """ % outdict

def getprojwkt(ifile, withgrid = False):
    import osr
    proj4str = getproj4(ifile, withgrid = withgrid)
    
    srs = osr.SpatialReference()
    # Imports WKT to Spatial Reference Object
    srs.ImportFromProj4(proj4str)
    srs.ExportToWkt() # converts the WKT to an ESRI-compatible format
    return srs.ExportToWkt()


def basemap_from_file(ifile, withgrid = False, **kwds):
    """
    Typically, the user will need to provide
    """
    proj4 = getproj4(ifile, withgrid = withgrid)
    basemap_options = basemap_options_from_proj4(proj4, **kwds)
    if 'llcrnrx' in basemap_options:
        if 'urcrnrx' in kwds:
            basemap_options['urcrnrx'] = kwds['urcrnrx']
        elif 'width' in kwds:
            basemap_options['urcrnrx'] = basemap_options['llcrnrx'] + kwds['width']
        elif 'x' in ifile.variables:
            x = ifile.variables['x']
            urx = x.max() + np.mean(np.diff(x))
            basemap_options['urcrnrx'] = urx
        else:
            raise KeyError('When a false_easting is available, the file must contain an x variable or the user must supply width or urcrnrx')
    if 'llcrnry' in basemap_options:
        if 'urcrnry' in kwds:
            basemap_options['urcrnry'] = kwds['urcrnry']
        elif 'height' in kwds:
            basemap_options['urcrnry'] = basemap_options['llcrnry'] + kwds['height']
        elif 'y' in ifile.variables:
            y = ifile.variables['y']
            ury = y.max() + np.mean(np.diff(y))
            basemap_options['urcrnry'] = ury
        else:
            raise KeyError('When a false_northing is available, the file must contain a y variable or the user must supply height or urcrnry')

    from mpl_toolkits.basemap import Basemap
    print(basemap_options)
    bmap = Basemap(**basemap_options)
    return bmap

def basemap_options_from_proj4(proj4, **kwds):
    """
    proj4 - string with projection optoins according to the proj4 system
    kwds - add keywords to control basemap specific options
        resolution = 'i' or 'c' or 'h' controls dpi of boundaries
        llcrnrlon=None, llcrnrlat=None, urcrnrlon=None, urcrnrlat=None,
        llcrnrx=None, llcrnry=None, urcrnrx=None, urcrnry=None,
        width=None, height=None,
    """
    excluded = ('proj', 'a', 'b', 'x_0', 'y_0', 'to_meter')
    dexpr = ''
    proj4_options = OrderedDict()
    for seg in proj4.split():
        if '=' in seg:
            k, v = seg.split('=')
            if k in ('+proj', '+ellps'):
                v = '"' + v + '"'
            proj4_options[k.replace('+', '')] = eval(v)
            
    basemap_options = dict([(k, v) for k, v in proj4_options.items() if k not in excluded])
    basemap_options['projection'] = proj4_options['proj']
    if 'a' in proj4_options and 'b' in proj4_options:
        basemap_options['rsphere'] = (proj4_options['a'], proj4_options['b'])
    elif 'a' in proj4_options and 'f' in proj4_options:
        basemap_options['rsphere'] = (proj4_options['a'], -(proj4_options['f'] * proj4_options['a'] - proj4_options['a']))
    elif 'a' in proj4_options:
        basemap_options['rsphere'] = (proj4_options['a'], proj4_options['a'])
    
    if 'x_0' in proj4_options:
        basemap_options['llcrnrx'] = -proj4_options['x_0']
    if 'y_0' in proj4_options:
        basemap_options['llcrnry'] = -proj4_options['y_0']
    basemap_options.update(**kwds)
    return basemap_options
    
def basemap_from_proj4(proj4, **kwds):
    from mpl_toolkits.basemap import Basemap
    basemap_options = basemap_options_from_proj4(proj4, **kwds)
    bmap = Basemap(**basemap_options)
    return bmap
    

def getproj4_from_cf_var(gridmapping, withgrid = False):
    mapstr_bits = OrderedDict()
    for pk in gridmapping.ncattrs():
        pv = getattr(gridmapping, pk)
        if pk == 'grid_mapping_name':
            pv4 = dict(lambert_conformal_conic = 'lcc',
                       rotated_latitude_longitude = 'ob_tran',
                       latitude_longitude = 'lonlat',
                       transverse_mercator = 'merc',
                       mercator = 'merc',
                       polar_stereographic = 'stere'
                       )[pv]
            mapstr_bits['proj'] = pv4
            if pv == 'rotated_latitude_longitude':
                mapstr_bits['o_proj'] = 'eqc'
        elif pk == 'standard_parallel':
            mapstr_bits['lat_1'] = pv[0]
            if len(pv) > 1:
                mapstr_bits['lat_2'] = pv[1]
        elif pk == 'longitude_of_central_meridian':
            mapstr_bits['lon_0'] = pv
        elif pk == 'latitude_of_projection_origin':
            mapstr_bits['lat_0'] = pv
        elif pk == 'false_easting':
            mapstr_bits['x_0'] = pv
        elif pk == 'false_northing':
            mapstr_bits['y_0'] = pv
        elif pk == 'scale_factor_at_projection_origin':
            mapstr_bits['k_0'] = pv
        elif pk == 'earth_radius':
            mapstr_bits['a'] = pv
            mapstr_bits['b'] = pv
        elif pk == 'semi_major_axis':
            mapstr_bits['a'] = pv
        elif pk == 'semi_minor_axis':
            mapstr_bits['b'] = pv
        elif pk == 'inverse_flattening':
            mapstr_bits['f'] = 1 / pv
        elif pk == 'grid_north_pole_latitude':
            mapstr_bits['o_lat_p'] = pv
        elif pk == 'grid_north_pole_longitude':
            mapstr_bits['lon_0'] = pv
        else:
            warn('Currently not using:' + str(pk) + ' ' + str(pv))

    # repr is required to prevent rounding of numpy array values        
    mapstr = ' '.join(['+%s=%s' % (k, v if isinstance(v, str) else repr(v)) for k, v in mapstr_bits.items()])
    return mapstr

def getproj(ifile, withgrid = False):
    import pyproj
    return pyproj.Proj(getproj4(ifile, withgrid = withgrid), preserve_units = withgrid)

def getproj4(ifile, withgrid = False):
    """
    Arguments:
      ifile - PseudoNetCDF file
      withgrid - True to include gridding parameters
    
    Returns:
      proj4str - string with proj4 parameters
    """
    from .conventions.ioapi import get_ioapi_sphere
    if getattr(ifile, 'GDTYP', 0) in (2, 7) and all([hasattr(ifile, k) for k in 'P_GAM P_ALP P_BET XORIG YORIG XCELL YCELL'.split()]):
        semi_major_axis, semi_minor_axis = get_ioapi_sphere()
        if ifile.GDTYP == 2:
            mapstr = '+proj=lcc +a=%s +b=%s +lon_0=%s +lat_1=%s +lat_2=%s +lat_0=%s' % (semi_major_axis, semi_minor_axis, ifile.P_GAM, ifile.P_ALP, ifile.P_BET, ifile.YCENT)
        elif ifile.GDTYP == 7:
            mapstr = '+proj=merc +a=%s +b=%s +lat_ts=0 +lon_0=%s' % (semi_major_axis, semi_minor_axis, ifile.XCENT)
        if withgrid:
            mapstr += ' +x_0=%s +y_0=%s +to_meter=%sm' % (-ifile.XORIG, -ifile.YORIG, ifile.XCELL)
    elif getattr(ifile, 'Conventions', getattr(ifile, 'CONVENTIONS', ''))[:2].upper() == 'CF':
        gridmappings = []
        for k, v in ifile.variables.items():
            if hasattr(v, 'grid_mapping'):
                gridmappings.append(getattr(v, 'grid_mapping'))
        
        if len(gridmappings) == 0:
            warn('No known grid mapping; assuming lonlat')
            mapstr = '+proj=lonlat'
        else:
            gridmappings = list(set(gridmappings))
            if len(gridmappings) > 1:
                warn('Using first grid mapping of ' + str(gridmappings))
            if not gridmappings[0] in ifile.variables:
                warn(gridmappings[0] + ' could not be found; assuming lonlat')
                mapstr = '+proj=lonlat'
            else:
                gridmapping = ifile.variables[gridmappings[0]]
                mapstr = getproj4_from_cf_var(gridmapping, withgrid = withgrid)
            
    mapstr += ' +no_defs'
    return mapstr


def getmap(ifile, resolution = 'i'):
    from mpl_toolkits.basemap import Basemap
    from .conventions.ioapi import get_ioapi_sphere
    if getattr(ifile, 'GDTYP', 0) in (2, 7) and all([hasattr(ifile, k) for k in 'P_GAM P_ALP P_BET XORIG YORIG XCELL YCELL'.split()]):
        try:
            NROWS = len(ifile.dimensions['ROW'])
            NCOLS = len(ifile.dimensions['COL'])
        except KeyError:
            NROWS = ifile.NROWS
            NCOLS = ifile.NCOLS
            
        llcrnrx = ifile.XORIG
        urcrnrx = ifile.XORIG + NCOLS * ifile.XCELL

        llcrnry = ifile.YORIG
        urcrnry = ifile.YORIG + NROWS * ifile.YCELL
        semi_major_axis, semi_minor_axis = get_ioapi_sphere()
        if ifile.GDTYP == 2:
            from mpl_toolkits.basemap import pyproj
            p = pyproj.Proj(proj='lcc',a = semi_major_axis, b = semi_major_axis, lon_0 = ifile.P_GAM, lat_1 = ifile.P_ALP, lat_2 = ifile.P_BET, lat_0 = ifile.YCENT)
            llcrnrlon, llcrnrlat = p(llcrnrx, llcrnry, inverse = True)
            urcrnrlon, urcrnrlat = p(urcrnrx, urcrnry, inverse = True)
            m = Basemap(projection = 'lcc', rsphere = (semi_major_axis, semi_major_axis), lon_0=ifile.P_GAM, lat_1 = ifile.P_ALP, lat_2 = ifile.P_BET, lat_0 = ifile.YCENT, llcrnrlon = llcrnrlon, llcrnrlat = llcrnrlat, urcrnrlat = urcrnrlat, urcrnrlon = urcrnrlon, resolution = resolution, suppress_ticks = False)
        elif ifile.GDTYP == 7:
            from mpl_toolkits.basemap import pyproj
            mapstr = '+proj=merc +a=%s +b=%s +lat_ts=0 +lon_0=%s' % (semi_major_axis, semi_major_axis, ifile.XCENT)
            p = pyproj.Proj(mapstr)
            #p = Proj(proj='merc',rsphere = (semi_major_axis, semi_major_axis), lat_ts = ifile.P_ALP, lat_0 = ifile.YCENT, lon_0 = ifile.XCENT)
            llcrnrlon, llcrnrlat = p(llcrnrx, llcrnry, inverse = True)
            urcrnrlon, urcrnrlat = p(urcrnrx, urcrnry, inverse = True)
            m = Basemap(projection = 'merc', rsphere = (semi_major_axis, semi_major_axis), lon_0=ifile.XCENT, lat_ts = 0, llcrnrlon = llcrnrlon, llcrnrlat = llcrnrlat, urcrnrlat = urcrnrlat, urcrnrlon = urcrnrlon, resolution = resolution, suppress_ticks = False)
        print('Found IO/API Mapping parameters')
    else:
        kwds = dict(suppress_ticks = False)
        try:
            lat, latunit = getlatbnds(ifile)
            lon, lonunit = getlonbnds(ifile)
            kwds['llcrnrlat'] = float(lat[:].min())
            kwds['urcrnrlat'] = float(lat[:].max())
            kwds['llcrnrlon'] = float(lon[:].min())
            kwds['urcrnrlon'] = float(lon[:].max())
            kwds['resolution'] = resolution
        except Exception as e:
            print(e)
            pass
        m = Basemap(**kwds)
    return m

