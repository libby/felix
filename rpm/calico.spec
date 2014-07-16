%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Name:           calico
Summary:        Project Calico virtual networking for cloud data centers
Version:        0.2
Release:        1%{?dist}
License:        Apache-2
URL:            http://projectcalico.org
Source0:        calico-%{version}.tar.gz
Source15:	calico-compute.init
Source25:	calico-compute.upstart
BuildArch:	noarch


%description
Project Calico is an open source solution for virtual networking in
cloud data centers. Its IP-centric architecture offers numerous
advantages over other cloud networking approaches such as VLANs and
overlays, including scalability, efficiency, and simplicity. It is
designed for a wide range of environments including OpenStack,
lightweight Linux containers (LXCs), bare metal, and Network Functions
Virtualization (NFV).


%package compute
Group:          Applications/Engineering
Summary:        Project Calico virtual networking for cloud data centers
Requires:       bird, calico-common, openstack-neutron, iptables

%description compute
This package provides the pieces needed on a compute node.

%post compute
if [ $1 -eq 1 ] ; then
    # Initial installation

    # Enable checksum calculation on DHCP responses.  This is needed
    # when sending DHCP responses over the TAP interfaces to guest
    # VMs, as apparently Linux doesn't itself do the checksum
    # calculation in that case.
    iptables -C POSTROUTING -t mangle -p udp --dport 68 -j CHECKSUM --checksum-fill ||
    iptables -A POSTROUTING -t mangle -p udp --dport 68 -j CHECKSUM --checksum-fill

    # Save current iptables for subsequent reboots.
    iptables-save > /etc/sysconfig/iptables

    # Enable IP forwarding.
    echo 1 > /proc/sys/net/ipv4/ip_forward

    /sbin/chkconfig --add calico-compute
    /sbin/service calico-compute start >/dev/null 2>&1
fi

%preun compute
if [ $1 -eq 0 ] ; then
    # Package removal, not upgrade
    /sbin/service calico-compute stop >/dev/null 2>&1
    /sbin/chkconfig --del calico-compute
fi

%postun compute
if [ $1 -ge 1 ] ; then
    # Package upgrade, not uninstall
    /sbin/service calico-compute condrestart >/dev/null 2>&1 || :
fi

%package control
Group:          Applications/Engineering
Summary:        Project Calico virtual networking for cloud data centers
Requires:       calico-common

%description control
This package provides the pieces needed on a controller node.


%package common
Group:          Applications/Engineering
Summary:        Project Calico virtual networking for cloud data centers

%description common
This package provides common files.


%prep
%setup -q


%build
%{__python} setup.py build

# Install sysv init scripts
install -p -D -m 755 %{SOURCE15} %{buildroot}%{_initrddir}/calico-compute

# Setup directories
install -d -m 755 %{buildroot}%{_datadir}/neutron

# Install upstart jobs examples
install -p -m 644 %{SOURCE25} %{buildroot}%{_datadir}/neutron/


%install
rm -rf $RPM_BUILD_ROOT
%{__python} setup.py install -O1 --skip-build --root $RPM_BUILD_ROOT


%clean
rm -rf $RPM_BUILD_ROOT


%files common
%defattr(-,root,root,-)
/usr/lib/python2.6/site-packages/calico*
%doc

%files compute
%defattr(-,root,root,-)
/usr/bin/*
/usr/etc/*
/usr/share/calico/*
%{_initrddir}/calico-compute
%{_datadir}/calico/calico-compute.upstart
%doc

%files control
%defattr(-,root,root,-)
%doc



%changelog