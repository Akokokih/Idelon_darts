"""Discrete projectile integration with external, profile-bound parameters."""
import math
from collections import deque
from .models import finite,integer,text


def application_model(profile_id,scale,amplitude_deg,launch_dx,launch_dy):
    """Profile-bound defaults from the measured scheduled-release solver."""
    return dict(model_type='discrete-ballistics-v1',profile_id=profile_id,scale=scale,
        amplitude_deg=amplitude_deg,trigger_delay_ns=27_448_847,input_overhead_ns=0,
        absolute_mouse_up=True,press_lead_ms=30.,phase_clock_base=1.1397210527997075,
        target_x_offset=-13*scale,launch_dx=launch_dx+9.6871557235*scale,
        launch_dy=launch_dy-3.1146662775*scale,intrinsic_angle_deg=-1.1340154181255302,
        algorithm='scheduled-release-v1',measured_red_rate=.65)


class DiscreteBallisticsModel:
    version='discrete-ballistics-v1'
    def __init__(self,data):
        self.profile_id=data['profile_id'];text('profile_id',self.profile_id)
        self.scale=data['scale'];finite('scale',self.scale,.1)
        if self.scale>10:raise ValueError('Échelle physique invalide')
        self.trigger_delay_ns=data.get('trigger_delay_ns',35_000_000)
        integer('trigger_delay_ns',self.trigger_delay_ns,0)
        if self.trigger_delay_ns>100_000_000:raise ValueError('Délai physique invalide')
        self.input_overhead_ns=data.get('input_overhead_ns',0)
        integer('input_overhead_ns',self.input_overhead_ns,0)
        if self.input_overhead_ns>50_000_000:raise ValueError('Budget d’entrée native invalide')
        self.absolute_mouse_up=data.get('absolute_mouse_up',False)
        if type(self.absolute_mouse_up) is not bool:raise ValueError('Mode de relâchement invalide')
        self.press_lead_ms=data.get('press_lead_ms',30.)
        finite('press_lead_ms',self.press_lead_ms,10)
        if self.press_lead_ms>50:raise ValueError('Avance d’appui invalide')
        self.target_x_offset=data.get('target_x_offset',-31.5)
        finite('target_x_offset',self.target_x_offset)
        self.intrinsic=math.radians(data.get('intrinsic_angle_deg',-1.1340154181255302))
        bias=data.get('launch_angle_bias_deg',0.)
        finite('launch_angle_bias_deg',bias)
        if abs(bias)>5:raise ValueError('Correction angulaire invalide')
        self.launch_bias=math.radians(bias)
        self.launch_dx=data.get('launch_dx',57*self.scale-5)
        self.launch_dy=data.get('launch_dy',2*self.scale-16)
        finite('launch_dx',self.launch_dx);finite('launch_dy',self.launch_dy)
        self.wind=(0.,0.);self.cache={};self.target_y_correction=0.
        self.contexts={key:dict(uncertainty_px=100.) for key in
                       ['wind-none','wind-vector',*data.get('reference_contexts',[])]}
        self.amplitude=math.radians(data.get('amplitude_deg',42.));self.centre=math.radians(20.)+self.intrinsic
        self.clock_base=data.get('phase_clock_base')
        if self.clock_base is not None:
            finite('phase_clock_base',self.clock_base,.5)
            if self.clock_base>3:raise ValueError('Horloge angulaire invalide')
        self.forecast_horizon_ns=45_000_000 if self.clock_base else 200_000_000
        self.forecast_policy='phase-clock-v2' if self.clock_base else 'harmonic-physics-v1'
        self.tick_mode=data.get('phase_tick_mode',False)
        if type(self.tick_mode) is not bool or (self.tick_mode and self.clock_base is None):raise ValueError('Horloge discrète invalide')
        if self.tick_mode:self.forecast_policy='phase-ticks-v3'
        self.tick_delay_fraction=data.get('tick_delay_fraction')
        if self.tick_delay_fraction is not None:
            finite('tick_delay_fraction',self.tick_delay_fraction,0)
            if self.tick_delay_fraction>3:raise ValueError('Délai discret invalide')
        self.phase_samples=deque(maxlen=128);self.phase_scene=None;self.phase_last=None;self.phase_diagnostics=None
        self.phase_frame_stamp=None;self.phase_target_half_height=None

    def observe_motion(self,observation):
        if self.clock_base is None:return
        scene=(observation.session_id,observation.segment_index,observation.launcher_position,
               observation.target_center,observation.context_key,observation.wind_features,self.amplitude)
        if scene!=self.phase_scene:
            self.phase_samples.clear();self.phase_last=None;self.phase_scene=scene;self.phase_frame_stamp=None
        angle=observation.arm_angle;stamp=observation.sample_ns or observation.capture_end_ns
        previous_frame=self.phase_frame_stamp;self.phase_frame_stamp=stamp
        self.phase_target_half_height=getattr(observation,'target_half_height',None)
        if angle is None or observation.arm_direction not in (-1,1):return
        if self.phase_last and angle==self.phase_last[1]:return
        if self.phase_last and not 0<stamp-self.phase_last[0]<=250_000_000:self.phase_samples.clear()
        self.phase_last=(stamp,angle)
        ratio=(angle-self.centre)/self.amplitude
        if abs(ratio)>.9:return
        phase=math.pi-math.asin(ratio) if observation.arm_direction==-1 else math.asin(ratio)
        lower=previous_frame if previous_frame is not None and 0<stamp-previous_frame<=100_000_000 else stamp-25_000_000
        self.phase_samples.append((stamp,phase,angle,ratio,lower))

    def fit_tick_clock(self,stamp):
        import numpy as np
        points=[p for p in self.phase_samples if 0<=stamp-p[0]<=650_000_000]
        if len(points)<6:return None
        times=np.array([(p[0]-stamp)/1e9 for p in points]);phases=np.unwrap([p[1] for p in points])
        if np.ptp(times)<.15:return None
        degrees=math.degrees(self.amplitude);hits=max(0.,30*(degrees-38)/max(.1,53-degrees))
        factor=1.5+(2.1+max(0.,(hits-50)/75))*hits/(hits+25)
        step=math.radians(1.3)*factor;period=math.radians(1.3)/self.clock_base
        weights=np.array([1-p[3]**2 for p in points]);values=np.array([p[2] for p in points])
        offset=float(np.angle(np.average(np.exp(2j*np.pi*phases/step),weights=weights))*step/(2*np.pi))
        ticks=np.rint((phases-offset)/step)
        errors=values-(self.centre+self.amplitude*np.sin(offset+ticks*step))
        valid=abs(errors)<=math.radians(.5)
        if np.count_nonzero(valid)<6 or np.mean(valid)<.8:return None
        rms=float(np.sqrt(np.mean(errors[valid]**2)))
        if rms>math.radians(.25):return None
        def temporal_fit(selected):
            n=ticks[selected];t=times[selected];w=weights[selected]
            mean_n=float(np.average(n,weights=w));mean_t=float(np.average(t,weights=w))
            centred=n-mean_n;denominator=float(np.sum(w*centred**2))
            if denominator<=0:return None
            slope=float(np.sum(w*centred*(t-mean_t))/denominator)
            return slope,mean_t-slope*mean_n,mean_n,float(np.sum(centred**2))
        fitted_time=temporal_fit(valid)
        if fitted_time is None:return None
        period,origin,_,_=fitted_time
        time_errors=times-(origin+ticks*period)
        mad=float(np.median(abs(time_errors[valid]-np.median(time_errors[valid]))))
        selected=valid&(abs(time_errors)<=max(.004,3*mad))
        if np.count_nonzero(selected)<6 or np.mean(selected)<.8:return None
        fitted_time=temporal_fit(selected)
        if fitted_time is None:return None
        period,origin,mean_n,spread=fitted_time
        if not .017<=period<=.045:return None
        time_errors=times[selected]-(origin+ticks[selected]*period)
        cadence_rms=float(np.sqrt(np.mean(time_errors**2)))
        if cadence_rms>.008 or abs(times[-1]-(origin+ticks[-1]*period))>.009:return None
        uncertainty=max(.001,cadence_rms*math.sqrt(1/np.count_nonzero(selected)+(ticks[-1]-mean_n)**2/max(spread,1.)))
        return dict(offset=offset,period=period,step=step,origin=origin,uncertainty=uncertainty,
                    phase=float(phases[-1]),points=int(np.count_nonzero(selected)),rms=rms,cadence_rms=cadence_rms,
                    max_error=float(np.max(abs(errors[valid]))))

    def tick_forecast(self,stamp,aim):
        clock=self.fit_tick_clock(stamp)
        if clock is None or self.phase_target_half_height is None:return None
        offset=clock['offset'];step=clock['step'];period=clock['period'];origin=clock['origin']
        target_phase=math.pi-math.asin(max(-.99,min(.99,(aim-self.centre)/self.amplitude)))
        target_phase+=round((clock['phase']-target_phase)/(2*math.pi))*2*math.pi
        centre_tick=round((target_phase-offset)/step)
        launcher,target,context=self.phase_scene[2:5]
        safe_half=self.phase_target_half_height-3*self.scale
        if safe_half<=0:return None
        impacts={}
        for tick in range(centre_tick-4,centre_tick+5):
            phase=offset+tick*step
            if math.cos(phase)>=-.1:continue
            angle=self.centre+self.amplitude*math.sin(phase)
            impact=self.impact(launcher,angle,target[0]+self.target_x_offset,context)
            if impact is not None:impacts[tick]=impact
        safe=[tick for tick,y in impacts.items() if abs(y-target[1])<=safe_half]
        if not safe:return None
        groups=[]
        for tick in sorted(safe):
            if groups and tick==groups[-1][-1]+1:groups[-1].append(tick)
            else:groups.append([tick])
        group=min(groups,key=lambda g:(-len(g),abs(sum(impacts[n] for n in g)/len(g)-target[1])))
        if len(group)<2:
            # A later sweep need not shift the game's pose lattice. Waiting for
            # two red poses can therefore block forever. One safe pose requires
            # a substantially more precise clock than a wider hold window.
            if clock['uncertainty']>.003:return None
        if clock['uncertainty']>.010:return None
        crossing=origin+((group[0]+group[-1])/2+.5)*period
        if not -.1<=crossing<=.15:return None
        phase_now=offset-origin/period*step;frequency=step/period
        omega=self.amplitude*math.cos(phase_now)*frequency
        if omega>=-.1:return None
        alpha=-self.amplitude*math.sin(phase_now)*frequency*frequency
        predicted=sum(impacts[n] for n in group)/len(group)
        self.phase_diagnostics=dict(points=clock['points'],frequency=frequency,rms_rad=clock['rms'],
            tick_period_ms=period*1000,tick_clock_uncertainty_ms=clock['uncertainty']*1000,
            tick_cadence_rms_ms=clock['cadence_rms']*1000,
            safe_tick_count=len(group),safe_tick_impacts=[impacts[n] for n in group],predicted_impact_y=predicted,
            effective_trigger_delay_ns=(round(self.tick_delay_fraction*period*1e9)
                                        if self.tick_delay_fraction is not None else self.trigger_delay_ns))
        return crossing,omega,alpha,clock['max_error']

    def clock_forecast(self,stamp,aim):
        import numpy as np
        if self.tick_mode:return self.tick_forecast(stamp,aim)
        points=[p for p in self.phase_samples if 0<=stamp-p[0]<=650_000_000]
        if len(points)<6:return None
        times=np.array([(p[0]-stamp)/1e9 for p in points]);phases=np.unwrap([p[1] for p in points])
        if np.ptp(times)<.15:return None
        degrees=math.degrees(self.amplitude)
        hits=max(0.,30*(degrees-38)/max(.1,53-degrees))
        frequency=self.clock_base*(1.5+(2.1+max(0.,(hits-50)/75))*hits/(hits+25))
        weights=np.array([1-p[3]**2 for p in points]);values=np.array([p[2] for p in points])
        offsets=phases-frequency*times;phase=float(np.average(offsets,weights=weights))
        errors=values-(self.centre+self.amplitude*np.sin(frequency*times+phase))
        valid=abs(errors)<=math.radians(.8)
        if np.count_nonzero(valid)<6 or np.mean(valid)<.8:return None
        phase=float(np.average(offsets[valid],weights=weights[valid]))
        errors=values[valid]-(self.centre+self.amplitude*np.sin(frequency*times[valid]+phase))
        residual=float(np.max(abs(errors)));rms=float(np.sqrt(np.mean(errors**2)))
        if residual>math.radians(.8) or rms>math.radians(.35):return None
        ratio=(aim-self.centre)/self.amplitude
        if abs(ratio)>=.97:return None
        target=math.pi-math.asin(ratio);target+=round((phase-target)/(2*math.pi))*2*math.pi
        crossing=(target-phase)/frequency
        if not -.1<=crossing<=.15:return None
        omega=self.amplitude*math.cos(phase)*frequency
        if omega>=-.1:return None
        alpha=-self.amplitude*math.sin(phase)*frequency*frequency
        self.phase_diagnostics=dict(points=int(np.count_nonzero(valid)),frequency=frequency,rms_rad=rms)
        return crossing,omega,alpha,residual

    def bind_observation(self,observation):
        features=observation.wind_features
        if observation.context_key=='wind-none':wind=(0.,0.)
        elif features is not None and len(features)==2:wind=tuple(features)
        else:raise ValueError('Vecteur de vent physique absent')
        if any(not math.isfinite(v) or abs(v)>35 for v in wind):raise ValueError('Vent hors domaine physique')
        if wind!=self.wind:self.cache.clear()
        self.wind=wind

    def effective_uncertainty(self,context):return 100.

    def impact(self,launcher,angle,target_x,context):
        if context not in self.contexts or not -.6<angle<1.3:return None
        theta=angle-self.intrinsic+self.launch_bias;s=self.scale
        x=launcher[0]+self.launch_dx
        y=launcher[1]+self.launch_dy-72*s*math.sin(theta)
        vx=5.2*s*math.cos(theta);vy=-5.2*s*math.sin(theta)
        ax=s*self.wind[0]/600;ay=s*(.033+self.wind[1]/750)
        if not x<target_x:return None
        for _ in range(800):
            x+=vx;y+=vy;vy+=ay;vx=max(s,vx+ax)
            if x>=target_x:return y
        return None

    def flight_steps(self,launcher,angle,target_x):
        theta=angle-self.intrinsic+self.launch_bias;s=self.scale
        x=launcher[0]+self.launch_dx;vx=5.2*s*math.cos(theta);ax=s*self.wind[0]/600
        for count in range(1,801):
            x+=vx;vx=max(s,vx+ax)
            if x>=target_x:return count
        return 800

    def aim_angle(self,launcher,target,context):
        if context not in self.contexts:return None
        key=(tuple(launcher),tuple(target),context,self.wind,self.target_y_correction,self.amplitude)
        if key in self.cache:return self.cache[key]
        low,high=max(-.5,self.centre-self.amplitude+.01),min(1.2,self.centre+self.amplitude-.01)
        desired=target[1]+self.target_y_correction
        candidates=[]
        grid=[low+(high-low)*i/64 for i in range(65)]
        values=[self.impact(launcher,a,target[0],context) for a in grid]
        # Long-distance shots may have both arcs below the target at the sweep
        # endpoints. Search every crossing, then prefer the lower flight arc.
        for left,right,before,after in zip(grid,grid[1:],values,values[1:]):
            if before is None or after is None or (before-desired)*(after-desired)>0:continue
            local=[]
            for _ in range(30):
                mid=(left+right)/2;y=self.impact(launcher,mid,target[0],context)
                local.append((abs(y-desired),mid))
                if (before-desired)*(y-desired)>0:left=mid;before=y
                else:right=mid
            candidates.append(min(local))
        if not candidates:return None
        tolerance=max(3.,2*self.scale)
        if self.tick_mode and self.phase_target_half_height is not None:tolerance=max(tolerance,.4*self.phase_target_half_height)
        acceptable=[(error,angle) for error,angle in candidates if error<=tolerance]
        angle=min(acceptable,key=lambda item:item[1])[1] if acceptable else min(candidates)[1]
        if self.tick_mode and acceptable:
            degrees=math.degrees(self.amplitude);hits=max(0.,30*(degrees-38)/max(.1,53-degrees))
            step=math.radians(1.3)*(1.5+(2.1+max(0.,(hits-50)/75))*hits/(hits+25))
            robust=[]
            for error,candidate in acceptable:
                ratio=(candidate-self.centre)/self.amplitude
                if abs(ratio)>.98:continue
                phase=math.pi-math.asin(ratio)
                ends=[self.impact(launcher,self.centre+self.amplitude*math.sin(phase+d),target[0],context)
                      for d in (-step/2,step/2)]
                if all(y is not None for y in ends):robust.append((max(abs(y-desired) for y in ends),candidate))
            if robust:angle=min(robust)[1]
        self.cache[key]=angle
        return angle

    def forecast(self,history,angle,aim):
        # A sinusoidal arm becomes linear after conversion to its descending phase.
        import numpy as np
        if self.clock_base is not None:return self.clock_forecast(history[-1][0],aim)
        if len(history)<3:return None
        h=list(history)[-6:];a=self.amplitude;c=self.centre
        values=np.array([v for _,v in h]);ratios=(values-c)/a
        target=(aim-c)/a
        if abs(target)>=.995:return None
        times=np.array([(t-h[-1][0])/1e9 for t,_ in h])
        valid=abs(ratios)<.97
        if np.count_nonzero(valid)<3:return None
        ratios=ratios[valid];values=values[valid];times=times[valid]
        phase=np.pi-np.arcsin(ratios)
        if np.ptp(times)<.03:return None
        frequency,intercept=np.polyfit(times,phase,1)
        fitted=c+a*np.sin(np.polyval([frequency,intercept],times))
        residual=float(np.max(abs(values-fitted)))
        tolerance=math.radians(.6*max(1.,1.25/self.scale))
        if not .4<frequency<12 or residual>tolerance:return None
        current=float(intercept)
        crossing=(math.pi-math.asin(target)-current)/frequency
        if not -.1<=crossing<=.3:return None
        omega=a*math.cos(current)*frequency;alpha=-a*math.sin(current)*frequency*frequency
        return crossing,float(omega),float(alpha),residual
