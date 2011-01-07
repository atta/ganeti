#
#

# Copyright (C) 2006, 2007, 2008, 2009, 2010, 2011 Google Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.


"""OpCodes module

This module implements the data structures which define the cluster
operations - the so-called opcodes.

Every operation which modifies the cluster state is expressed via
opcodes.

"""

# this are practically structures, so disable the message about too
# few public methods:
# pylint: disable-msg=R0903

import logging

from ganeti import constants
from ganeti import errors
from ganeti import ht


# Common opcode attributes

#: output fields for a query operation
_POutputFields = ("output_fields", ht.NoDefault, ht.TListOf(ht.TNonEmptyString))

#: the shutdown timeout
_PShutdownTimeout = ("shutdown_timeout", constants.DEFAULT_SHUTDOWN_TIMEOUT,
                     ht.TPositiveInt)

#: the force parameter
_PForce = ("force", False, ht.TBool)

#: a required instance name (for single-instance LUs)
_PInstanceName = ("instance_name", ht.NoDefault, ht.TNonEmptyString)

#: Whether to ignore offline nodes
_PIgnoreOfflineNodes = ("ignore_offline_nodes", False, ht.TBool)

#: a required node name (for single-node LUs)
_PNodeName = ("node_name", ht.NoDefault, ht.TNonEmptyString)

#: a required node group name (for single-group LUs)
_PGroupName = ("group_name", ht.NoDefault, ht.TNonEmptyString)

#: Migration type (live/non-live)
_PMigrationMode = ("mode", None,
                   ht.TOr(ht.TNone, ht.TElemOf(constants.HT_MIGRATION_MODES)))

#: Obsolete 'live' migration mode (boolean)
_PMigrationLive = ("live", None, ht.TMaybeBool)

#: Tag type
_PTagKind = ("kind", ht.NoDefault, ht.TElemOf(constants.VALID_TAG_TYPES))

#: List of tag strings
_PTags = ("tags", ht.NoDefault, ht.TListOf(ht.TNonEmptyString))


def RequireFileStorage():
  """Checks that file storage is enabled.

  While it doesn't really fit into this module, L{utils} was deemed too large
  of a dependency to be imported for just one or two functions.

  @raise errors.OpPrereqError: when file storage is disabled

  """
  if not constants.ENABLE_FILE_STORAGE:
    raise errors.OpPrereqError("File storage disabled at configure time",
                               errors.ECODE_INVAL)


def _CheckDiskTemplate(template):
  """Ensure a given disk template is valid.

  """
  if template not in constants.DISK_TEMPLATES:
    # Using str.join directly to avoid importing utils for CommaJoin
    msg = ("Invalid disk template name '%s', valid templates are: %s" %
           (template, ", ".join(constants.DISK_TEMPLATES)))
    raise errors.OpPrereqError(msg, errors.ECODE_INVAL)
  if template == constants.DT_FILE:
    RequireFileStorage()
  return True


def _CheckStorageType(storage_type):
  """Ensure a given storage type is valid.

  """
  if storage_type not in constants.VALID_STORAGE_TYPES:
    raise errors.OpPrereqError("Unknown storage type: %s" % storage_type,
                               errors.ECODE_INVAL)
  if storage_type == constants.ST_FILE:
    RequireFileStorage()
  return True


#: Storage type parameter
_PStorageType = ("storage_type", ht.NoDefault, _CheckStorageType)


class _AutoOpParamSlots(type):
  """Meta class for opcode definitions.

  """
  def __new__(mcs, name, bases, attrs):
    """Called when a class should be created.

    @param mcs: The meta class
    @param name: Name of created class
    @param bases: Base classes
    @type attrs: dict
    @param attrs: Class attributes

    """
    assert "__slots__" not in attrs, \
      "Class '%s' defines __slots__ when it should use OP_PARAMS" % name
    assert "OP_ID" in attrs, "Class '%s' is missing OP_ID attribute" % name

    # Always set OP_PARAMS to avoid duplicates in BaseOpCode.GetAllParams
    params = attrs.setdefault("OP_PARAMS", [])

    # Use parameter names as slots
    slots = [pname for (pname, _, _) in params]

    assert "OP_DSC_FIELD" not in attrs or attrs["OP_DSC_FIELD"] in slots, \
      "Class '%s' uses unknown field in OP_DSC_FIELD" % name

    attrs["__slots__"] = slots

    return type.__new__(mcs, name, bases, attrs)


class BaseOpCode(object):
  """A simple serializable object.

  This object serves as a parent class for OpCode without any custom
  field handling.

  """
  __metaclass__ = _AutoOpParamSlots

  OP_ID = None

  def __init__(self, **kwargs):
    """Constructor for BaseOpCode.

    The constructor takes only keyword arguments and will set
    attributes on this object based on the passed arguments. As such,
    it means that you should not pass arguments which are not in the
    __slots__ attribute for this class.

    """
    slots = self._all_slots()
    for key in kwargs:
      if key not in slots:
        raise TypeError("Object %s doesn't support the parameter '%s'" %
                        (self.__class__.__name__, key))
      setattr(self, key, kwargs[key])

  def __getstate__(self):
    """Generic serializer.

    This method just returns the contents of the instance as a
    dictionary.

    @rtype:  C{dict}
    @return: the instance attributes and their values

    """
    state = {}
    for name in self._all_slots():
      if hasattr(self, name):
        state[name] = getattr(self, name)
    return state

  def __setstate__(self, state):
    """Generic unserializer.

    This method just restores from the serialized state the attributes
    of the current instance.

    @param state: the serialized opcode data
    @type state:  C{dict}

    """
    if not isinstance(state, dict):
      raise ValueError("Invalid data to __setstate__: expected dict, got %s" %
                       type(state))

    for name in self._all_slots():
      if name not in state and hasattr(self, name):
        delattr(self, name)

    for name in state:
      setattr(self, name, state[name])

  @classmethod
  def _all_slots(cls):
    """Compute the list of all declared slots for a class.

    """
    slots = []
    for parent in cls.__mro__:
      slots.extend(getattr(parent, "__slots__", []))
    return slots

  @classmethod
  def GetAllParams(cls):
    """Compute list of all parameters for an opcode.

    """
    slots = []
    for parent in cls.__mro__:
      slots.extend(getattr(parent, "OP_PARAMS", []))
    return slots

  def Validate(self, set_defaults):
    """Validate opcode parameters, optionally setting default values.

    @type set_defaults: bool
    @param set_defaults: Whether to set default values
    @raise errors.OpPrereqError: When a parameter value doesn't match
                                 requirements

    """
    for (attr_name, default, test) in self.GetAllParams():
      assert test == ht.NoType or callable(test)

      if not hasattr(self, attr_name):
        if default == ht.NoDefault:
          raise errors.OpPrereqError("Required parameter '%s.%s' missing" %
                                     (self.OP_ID, attr_name),
                                     errors.ECODE_INVAL)
        elif set_defaults:
          if callable(default):
            dval = default()
          else:
            dval = default
          setattr(self, attr_name, dval)

      if test == ht.NoType:
        # no tests here
        continue

      if set_defaults or hasattr(self, attr_name):
        attr_val = getattr(self, attr_name)
        if not test(attr_val):
          logging.error("OpCode %s, parameter %s, has invalid type %s/value %s",
                        self.OP_ID, attr_name, type(attr_val), attr_val)
          raise errors.OpPrereqError("Parameter '%s.%s' fails validation" %
                                     (self.OP_ID, attr_name),
                                     errors.ECODE_INVAL)


class OpCode(BaseOpCode):
  """Abstract OpCode.

  This is the root of the actual OpCode hierarchy. All clases derived
  from this class should override OP_ID.

  @cvar OP_ID: The ID of this opcode. This should be unique amongst all
               children of this class.
  @cvar OP_DSC_FIELD: The name of a field whose value will be included in the
                      string returned by Summary(); see the docstring of that
                      method for details).
  @cvar OP_PARAMS: List of opcode attributes, the default values they should
                   get if not already defined, and types they must match.
  @cvar WITH_LU: Boolean that specifies whether this should be included in
      mcpu's dispatch table
  @ivar dry_run: Whether the LU should be run in dry-run mode, i.e. just
                 the check steps
  @ivar priority: Opcode priority for queue

  """
  OP_ID = "OP_ABSTRACT"
  WITH_LU = True
  OP_PARAMS = [
    ("dry_run", None, ht.TMaybeBool),
    ("debug_level", None, ht.TOr(ht.TNone, ht.TPositiveInt)),
    ("priority", constants.OP_PRIO_DEFAULT,
     ht.TElemOf(constants.OP_PRIO_SUBMIT_VALID)),
    ]

  def __getstate__(self):
    """Specialized getstate for opcodes.

    This method adds to the state dictionary the OP_ID of the class,
    so that on unload we can identify the correct class for
    instantiating the opcode.

    @rtype:   C{dict}
    @return:  the state as a dictionary

    """
    data = BaseOpCode.__getstate__(self)
    data["OP_ID"] = self.OP_ID
    return data

  @classmethod
  def LoadOpCode(cls, data):
    """Generic load opcode method.

    The method identifies the correct opcode class from the dict-form
    by looking for a OP_ID key, if this is not found, or its value is
    not available in this module as a child of this class, we fail.

    @type data:  C{dict}
    @param data: the serialized opcode

    """
    if not isinstance(data, dict):
      raise ValueError("Invalid data to LoadOpCode (%s)" % type(data))
    if "OP_ID" not in data:
      raise ValueError("Invalid data to LoadOpcode, missing OP_ID")
    op_id = data["OP_ID"]
    op_class = None
    if op_id in OP_MAPPING:
      op_class = OP_MAPPING[op_id]
    else:
      raise ValueError("Invalid data to LoadOpCode: OP_ID %s unsupported" %
                       op_id)
    op = op_class()
    new_data = data.copy()
    del new_data["OP_ID"]
    op.__setstate__(new_data)
    return op

  def Summary(self):
    """Generates a summary description of this opcode.

    The summary is the value of the OP_ID attribute (without the "OP_" prefix),
    plus the value of the OP_DSC_FIELD attribute, if one was defined; this field
    should allow to easily identify the operation (for an instance creation job,
    e.g., it would be the instance name).

    """
    # all OP_ID start with OP_, we remove that
    txt = self.OP_ID[3:]
    field_name = getattr(self, "OP_DSC_FIELD", None)
    if field_name:
      field_value = getattr(self, field_name, None)
      if isinstance(field_value, (list, tuple)):
        field_value = ",".join(str(i) for i in field_value)
      txt = "%s(%s)" % (txt, field_value)
    return txt


# cluster opcodes

class OpPostInitCluster(OpCode):
  """Post cluster initialization.

  This opcode does not touch the cluster at all. Its purpose is to run hooks
  after the cluster has been initialized.

  """
  OP_ID = "OP_CLUSTER_POST_INIT"


class OpDestroyCluster(OpCode):
  """Destroy the cluster.

  This opcode has no other parameters. All the state is irreversibly
  lost after the execution of this opcode.

  """
  OP_ID = "OP_CLUSTER_DESTROY"


class OpQueryClusterInfo(OpCode):
  """Query cluster information."""
  OP_ID = "OP_CLUSTER_QUERY"


class OpVerifyCluster(OpCode):
  """Verify the cluster state.

  @type skip_checks: C{list}
  @ivar skip_checks: steps to be skipped from the verify process; this
                     needs to be a subset of
                     L{constants.VERIFY_OPTIONAL_CHECKS}; currently
                     only L{constants.VERIFY_NPLUSONE_MEM} can be passed

  """
  OP_ID = "OP_CLUSTER_VERIFY"
  OP_PARAMS = [
    ("skip_checks", ht.EmptyList,
     ht.TListOf(ht.TElemOf(constants.VERIFY_OPTIONAL_CHECKS))),
    ("verbose", False, ht.TBool),
    ("error_codes", False, ht.TBool),
    ("debug_simulate_errors", False, ht.TBool),
    ]


class OpVerifyDisks(OpCode):
  """Verify the cluster disks.

  Parameters: none

  Result: a tuple of four elements:
    - list of node names with bad data returned (unreachable, etc.)
    - dict of node names with broken volume groups (values: error msg)
    - list of instances with degraded disks (that should be activated)
    - dict of instances with missing logical volumes (values: (node, vol)
      pairs with details about the missing volumes)

  In normal operation, all lists should be empty. A non-empty instance
  list (3rd element of the result) is still ok (errors were fixed) but
  non-empty node list means some node is down, and probably there are
  unfixable drbd errors.

  Note that only instances that are drbd-based are taken into
  consideration. This might need to be revisited in the future.

  """
  OP_ID = "OP_CLUSTER_VERIFY_DISKS"


class OpRepairDiskSizes(OpCode):
  """Verify the disk sizes of the instances and fixes configuration
  mimatches.

  Parameters: optional instances list, in case we want to restrict the
  checks to only a subset of the instances.

  Result: a list of tuples, (instance, disk, new-size) for changed
  configurations.

  In normal operation, the list should be empty.

  @type instances: list
  @ivar instances: the list of instances to check, or empty for all instances

  """
  OP_ID = "OP_CLUSTER_REPAIR_DISK_SIZES"
  OP_PARAMS = [
    ("instances", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ]


class OpQueryConfigValues(OpCode):
  """Query cluster configuration values."""
  OP_ID = "OP_CLUSTER_CONFIG_QUERY"
  OP_PARAMS = [
    _POutputFields
    ]


class OpRenameCluster(OpCode):
  """Rename the cluster.

  @type name: C{str}
  @ivar name: The new name of the cluster. The name and/or the master IP
              address will be changed to match the new name and its IP
              address.

  """
  OP_ID = "OP_CLUSTER_RENAME"
  OP_DSC_FIELD = "name"
  OP_PARAMS = [
    ("name", ht.NoDefault, ht.TNonEmptyString),
    ]


class OpSetClusterParams(OpCode):
  """Change the parameters of the cluster.

  @type vg_name: C{str} or C{None}
  @ivar vg_name: The new volume group name or None to disable LVM usage.

  """
  OP_ID = "OP_CLUSTER_SET_PARAMS"
  OP_PARAMS = [
    ("vg_name", None, ht.TMaybeString),
    ("enabled_hypervisors", None,
     ht.TOr(ht.TAnd(ht.TListOf(ht.TElemOf(constants.HYPER_TYPES)), ht.TTrue),
            ht.TNone)),
    ("hvparams", None, ht.TOr(ht.TDictOf(ht.TNonEmptyString, ht.TDict),
                              ht.TNone)),
    ("beparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ("os_hvp", None, ht.TOr(ht.TDictOf(ht.TNonEmptyString, ht.TDict),
                            ht.TNone)),
    ("osparams", None, ht.TOr(ht.TDictOf(ht.TNonEmptyString, ht.TDict),
                              ht.TNone)),
    ("candidate_pool_size", None, ht.TOr(ht.TStrictPositiveInt, ht.TNone)),
    ("uid_pool", None, ht.NoType),
    ("add_uids", None, ht.NoType),
    ("remove_uids", None, ht.NoType),
    ("maintain_node_health", None, ht.TMaybeBool),
    ("prealloc_wipe_disks", None, ht.TMaybeBool),
    ("nicparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ("ndparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ("drbd_helper", None, ht.TOr(ht.TString, ht.TNone)),
    ("default_iallocator", None, ht.TOr(ht.TString, ht.TNone)),
    ("master_netdev", None, ht.TOr(ht.TString, ht.TNone)),
    ("reserved_lvs", None, ht.TOr(ht.TListOf(ht.TNonEmptyString), ht.TNone)),
    ("hidden_os", None, ht.TOr(ht.TListOf(
          ht.TAnd(ht.TList,
                ht.TIsLength(2),
                ht.TMap(lambda v: v[0], ht.TElemOf(constants.DDMS_VALUES)))),
          ht.TNone)),
    ("blacklisted_os", None, ht.TOr(ht.TListOf(
          ht.TAnd(ht.TList,
                ht.TIsLength(2),
                ht.TMap(lambda v: v[0], ht.TElemOf(constants.DDMS_VALUES)))),
          ht.TNone)),
    ]


class OpRedistributeConfig(OpCode):
  """Force a full push of the cluster configuration.

  """
  OP_ID = "OP_CLUSTER_REDIST_CONF"


class OpQuery(OpCode):
  """Query for resources/items.

  @ivar what: Resources to query for, must be one of L{constants.QR_OP_QUERY}
  @ivar fields: List of fields to retrieve
  @ivar filter: Query filter

  """
  OP_ID = "OP_QUERY"
  OP_PARAMS = [
    ("what", ht.NoDefault, ht.TElemOf(constants.QR_OP_QUERY)),
    ("fields", ht.NoDefault, ht.TListOf(ht.TNonEmptyString)),
    ("filter", None, ht.TOr(ht.TNone,
                            ht.TListOf(ht.TOr(ht.TNonEmptyString, ht.TList)))),
    ]


class OpQueryFields(OpCode):
  """Query for available resource/item fields.

  @ivar what: Resources to query for, must be one of L{constants.QR_OP_QUERY}
  @ivar fields: List of fields to retrieve

  """
  OP_ID = "OP_QUERY_FIELDS"
  OP_PARAMS = [
    ("what", ht.NoDefault, ht.TElemOf(constants.QR_OP_QUERY)),
    ("fields", None, ht.TOr(ht.TNone, ht.TListOf(ht.TNonEmptyString))),
    ]


class OpOobCommand(OpCode):
  """Interact with OOB."""
  OP_ID = "OP_OOB_COMMAND"
  OP_PARAMS = [
    _PNodeName,
    ("command", None, ht.TElemOf(constants.OOB_COMMANDS)),
    ("timeout", constants.OOB_TIMEOUT, ht.TInt),
    ]


# node opcodes

class OpRemoveNode(OpCode):
  """Remove a node.

  @type node_name: C{str}
  @ivar node_name: The name of the node to remove. If the node still has
                   instances on it, the operation will fail.

  """
  OP_ID = "OP_NODE_REMOVE"
  OP_DSC_FIELD = "node_name"
  OP_PARAMS = [
    _PNodeName,
    ]


class OpAddNode(OpCode):
  """Add a node to the cluster.

  @type node_name: C{str}
  @ivar node_name: The name of the node to add. This can be a short name,
                   but it will be expanded to the FQDN.
  @type primary_ip: IP address
  @ivar primary_ip: The primary IP of the node. This will be ignored when the
                    opcode is submitted, but will be filled during the node
                    add (so it will be visible in the job query).
  @type secondary_ip: IP address
  @ivar secondary_ip: The secondary IP of the node. This needs to be passed
                      if the cluster has been initialized in 'dual-network'
                      mode, otherwise it must not be given.
  @type readd: C{bool}
  @ivar readd: Whether to re-add an existing node to the cluster. If
               this is not passed, then the operation will abort if the node
               name is already in the cluster; use this parameter to 'repair'
               a node that had its configuration broken, or was reinstalled
               without removal from the cluster.
  @type group: C{str}
  @ivar group: The node group to which this node will belong.
  @type vm_capable: C{bool}
  @ivar vm_capable: The vm_capable node attribute
  @type master_capable: C{bool}
  @ivar master_capable: The master_capable node attribute

  """
  OP_ID = "OP_NODE_ADD"
  OP_DSC_FIELD = "node_name"
  OP_PARAMS = [
    _PNodeName,
    ("primary_ip", None, ht.NoType),
    ("secondary_ip", None, ht.TMaybeString),
    ("readd", False, ht.TBool),
    ("group", None, ht.TMaybeString),
    ("master_capable", None, ht.TMaybeBool),
    ("vm_capable", None, ht.TMaybeBool),
    ("ndparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ]


class OpQueryNodes(OpCode):
  """Compute the list of nodes."""
  OP_ID = "OP_NODE_QUERY"
  OP_PARAMS = [
    _POutputFields,
    ("names", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ("use_locking", False, ht.TBool),
    ]


class OpQueryNodeVolumes(OpCode):
  """Get list of volumes on node."""
  OP_ID = "OP_NODE_QUERYVOLS"
  OP_PARAMS = [
    _POutputFields,
    ("nodes", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ]


class OpQueryNodeStorage(OpCode):
  """Get information on storage for node(s)."""
  OP_ID = "OP_NODE_QUERY_STORAGE"
  OP_PARAMS = [
    _POutputFields,
    _PStorageType,
    ("nodes", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ("name", None, ht.TMaybeString),
    ]


class OpModifyNodeStorage(OpCode):
  """Modifies the properies of a storage unit"""
  OP_ID = "OP_NODE_MODIFY_STORAGE"
  OP_PARAMS = [
    _PNodeName,
    _PStorageType,
    ("name", ht.NoDefault, ht.TNonEmptyString),
    ("changes", ht.NoDefault, ht.TDict),
    ]


class OpRepairNodeStorage(OpCode):
  """Repairs the volume group on a node."""
  OP_ID = "OP_REPAIR_NODE_STORAGE"
  OP_DSC_FIELD = "node_name"
  OP_PARAMS = [
    _PNodeName,
    _PStorageType,
    ("name", ht.NoDefault, ht.TNonEmptyString),
    ("ignore_consistency", False, ht.TBool),
    ]


class OpSetNodeParams(OpCode):
  """Change the parameters of a node."""
  OP_ID = "OP_NODE_SET_PARAMS"
  OP_DSC_FIELD = "node_name"
  OP_PARAMS = [
    _PNodeName,
    _PForce,
    ("master_candidate", None, ht.TMaybeBool),
    ("offline", None, ht.TMaybeBool),
    ("drained", None, ht.TMaybeBool),
    ("auto_promote", False, ht.TBool),
    ("master_capable", None, ht.TMaybeBool),
    ("vm_capable", None, ht.TMaybeBool),
    ("secondary_ip", None, ht.TMaybeString),
    ("ndparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ("powered", None, ht.TMaybeBool),
    ]


class OpPowercycleNode(OpCode):
  """Tries to powercycle a node."""
  OP_ID = "OP_NODE_POWERCYCLE"
  OP_DSC_FIELD = "node_name"
  OP_PARAMS = [
    _PNodeName,
    _PForce,
    ]


class OpMigrateNode(OpCode):
  """Migrate all instances from a node."""
  OP_ID = "OP_NODE_MIGRATE"
  OP_DSC_FIELD = "node_name"
  OP_PARAMS = [
    _PNodeName,
    _PMigrationMode,
    _PMigrationLive,
    ]


class OpNodeEvacuationStrategy(OpCode):
  """Compute the evacuation strategy for a list of nodes."""
  OP_ID = "OP_NODE_EVAC_STRATEGY"
  OP_DSC_FIELD = "nodes"
  OP_PARAMS = [
    ("nodes", ht.NoDefault, ht.TListOf(ht.TNonEmptyString)),
    ("remote_node", None, ht.TMaybeString),
    ("iallocator", None, ht.TMaybeString),
    ]


# instance opcodes

class OpCreateInstance(OpCode):
  """Create an instance.

  @ivar instance_name: Instance name
  @ivar mode: Instance creation mode (one of L{constants.INSTANCE_CREATE_MODES})
  @ivar source_handshake: Signed handshake from source (remote import only)
  @ivar source_x509_ca: Source X509 CA in PEM format (remote import only)
  @ivar source_instance_name: Previous name of instance (remote import only)
  @ivar source_shutdown_timeout: Shutdown timeout used for source instance
    (remote import only)

  """
  OP_ID = "OP_INSTANCE_CREATE"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    ("beparams", ht.EmptyDict, ht.TDict),
    ("disks", ht.NoDefault, ht.TListOf(ht.TDict)),
    ("disk_template", ht.NoDefault, _CheckDiskTemplate),
    ("file_driver", None, ht.TOr(ht.TNone, ht.TElemOf(constants.FILE_DRIVER))),
    ("file_storage_dir", None, ht.TMaybeString),
    ("force_variant", False, ht.TBool),
    ("hvparams", ht.EmptyDict, ht.TDict),
    ("hypervisor", None, ht.TMaybeString),
    ("iallocator", None, ht.TMaybeString),
    ("identify_defaults", False, ht.TBool),
    ("ip_check", True, ht.TBool),
    ("mode", ht.NoDefault, ht.TElemOf(constants.INSTANCE_CREATE_MODES)),
    ("name_check", True, ht.TBool),
    ("nics", ht.NoDefault, ht.TListOf(ht.TDict)),
    ("no_install", None, ht.TMaybeBool),
    ("osparams", ht.EmptyDict, ht.TDict),
    ("os_type", None, ht.TMaybeString),
    ("pnode", None, ht.TMaybeString),
    ("snode", None, ht.TMaybeString),
    ("source_handshake", None, ht.TOr(ht.TList, ht.TNone)),
    ("source_instance_name", None, ht.TMaybeString),
    ("source_shutdown_timeout", constants.DEFAULT_SHUTDOWN_TIMEOUT,
     ht.TPositiveInt),
    ("source_x509_ca", None, ht.TMaybeString),
    ("src_node", None, ht.TMaybeString),
    ("src_path", None, ht.TMaybeString),
    ("start", True, ht.TBool),
    ("wait_for_sync", True, ht.TBool),
    ]


class OpReinstallInstance(OpCode):
  """Reinstall an instance's OS."""
  OP_ID = "OP_INSTANCE_REINSTALL"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    ("os_type", None, ht.TMaybeString),
    ("force_variant", False, ht.TBool),
    ("osparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ]


class OpRemoveInstance(OpCode):
  """Remove an instance."""
  OP_ID = "OP_INSTANCE_REMOVE"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PShutdownTimeout,
    ("ignore_failures", False, ht.TBool),
    ]


class OpRenameInstance(OpCode):
  """Rename an instance."""
  OP_ID = "OP_INSTANCE_RENAME"
  OP_PARAMS = [
    _PInstanceName,
    ("new_name", ht.NoDefault, ht.TNonEmptyString),
    ("ip_check", False, ht.TBool),
    ("name_check", True, ht.TBool),
    ]


class OpStartupInstance(OpCode):
  """Startup an instance."""
  OP_ID = "OP_INSTANCE_STARTUP"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PForce,
    _PIgnoreOfflineNodes,
    ("hvparams", ht.EmptyDict, ht.TDict),
    ("beparams", ht.EmptyDict, ht.TDict),
    ]


class OpShutdownInstance(OpCode):
  """Shutdown an instance."""
  OP_ID = "OP_INSTANCE_SHUTDOWN"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PIgnoreOfflineNodes,
    ("timeout", constants.DEFAULT_SHUTDOWN_TIMEOUT, ht.TPositiveInt),
    ]


class OpRebootInstance(OpCode):
  """Reboot an instance."""
  OP_ID = "OP_INSTANCE_REBOOT"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PShutdownTimeout,
    ("ignore_secondaries", False, ht.TBool),
    ("reboot_type", ht.NoDefault, ht.TElemOf(constants.REBOOT_TYPES)),
    ]


class OpReplaceDisks(OpCode):
  """Replace the disks of an instance."""
  OP_ID = "OP_INSTANCE_REPLACE_DISKS"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    ("mode", ht.NoDefault, ht.TElemOf(constants.REPLACE_MODES)),
    ("disks", ht.EmptyList, ht.TListOf(ht.TPositiveInt)),
    ("remote_node", None, ht.TMaybeString),
    ("iallocator", None, ht.TMaybeString),
    ("early_release", False, ht.TBool),
    ]


class OpFailoverInstance(OpCode):
  """Failover an instance."""
  OP_ID = "OP_INSTANCE_FAILOVER"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PShutdownTimeout,
    ("ignore_consistency", False, ht.TBool),
    ]


class OpMigrateInstance(OpCode):
  """Migrate an instance.

  This migrates (without shutting down an instance) to its secondary
  node.

  @ivar instance_name: the name of the instance
  @ivar mode: the migration mode (live, non-live or None for auto)

  """
  OP_ID = "OP_INSTANCE_MIGRATE"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PMigrationMode,
    _PMigrationLive,
    ("cleanup", False, ht.TBool),
    ]


class OpMoveInstance(OpCode):
  """Move an instance.

  This move (with shutting down an instance and data copying) to an
  arbitrary node.

  @ivar instance_name: the name of the instance
  @ivar target_node: the destination node

  """
  OP_ID = "OP_INSTANCE_MOVE"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PShutdownTimeout,
    ("target_node", ht.NoDefault, ht.TNonEmptyString),
    ]


class OpConnectConsole(OpCode):
  """Connect to an instance's console."""
  OP_ID = "OP_INSTANCE_CONSOLE"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName
    ]


class OpActivateInstanceDisks(OpCode):
  """Activate an instance's disks."""
  OP_ID = "OP_INSTANCE_ACTIVATE_DISKS"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    ("ignore_size", False, ht.TBool),
    ]


class OpDeactivateInstanceDisks(OpCode):
  """Deactivate an instance's disks."""
  OP_ID = "OP_INSTANCE_DEACTIVATE_DISKS"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName
    ]


class OpRecreateInstanceDisks(OpCode):
  """Deactivate an instance's disks."""
  OP_ID = "OP_INSTANCE_RECREATE_DISKS"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    ("disks", ht.EmptyList, ht.TListOf(ht.TPositiveInt)),
    ]


class OpQueryInstances(OpCode):
  """Compute the list of instances."""
  OP_ID = "OP_INSTANCE_QUERY"
  OP_PARAMS = [
    _POutputFields,
    ("names", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ("use_locking", False, ht.TBool),
    ]


class OpQueryInstanceData(OpCode):
  """Compute the run-time status of instances."""
  OP_ID = "OP_INSTANCE_QUERY_DATA"
  OP_PARAMS = [
    ("instances", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ("static", False, ht.TBool),
    ]


class OpSetInstanceParams(OpCode):
  """Change the parameters of an instance."""
  OP_ID = "OP_INSTANCE_SET_PARAMS"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PForce,
    ("nics", ht.EmptyList, ht.TList),
    ("disks", ht.EmptyList, ht.TList),
    ("beparams", ht.EmptyDict, ht.TDict),
    ("hvparams", ht.EmptyDict, ht.TDict),
    ("disk_template", None, ht.TOr(ht.TNone, _CheckDiskTemplate)),
    ("remote_node", None, ht.TMaybeString),
    ("os_name", None, ht.TMaybeString),
    ("force_variant", False, ht.TBool),
    ("osparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ]


class OpGrowDisk(OpCode):
  """Grow a disk of an instance."""
  OP_ID = "OP_INSTANCE_GROW_DISK"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    ("disk", ht.NoDefault, ht.TInt),
    ("amount", ht.NoDefault, ht.TInt),
    ("wait_for_sync", True, ht.TBool),
    ]


# Node group opcodes

class OpAddGroup(OpCode):
  """Add a node group to the cluster."""
  OP_ID = "OP_GROUP_ADD"
  OP_DSC_FIELD = "group_name"
  OP_PARAMS = [
    _PGroupName,
    ("ndparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ("alloc_policy", None,
     ht.TOr(ht.TNone, ht.TElemOf(constants.VALID_ALLOC_POLICIES))),
    ]


class OpAssignGroupNodes(OpCode):
  """Assign nodes to a node group."""
  OP_ID = "OP_ASSIGN_NODES"
  OP_DSC_FIELD = "group_name"
  OP_PARAMS = [
    _PGroupName,
    _PForce,
    ("nodes", ht.NoDefault, ht.TListOf(ht.TNonEmptyString)),
    ]


class OpQueryGroups(OpCode):
  """Compute the list of node groups."""
  OP_ID = "OP_GROUP_QUERY"
  OP_PARAMS = [
    _POutputFields,
    ("names", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ]


class OpSetGroupParams(OpCode):
  """Change the parameters of a node group."""
  OP_ID = "OP_GROUP_SET_PARAMS"
  OP_DSC_FIELD = "group_name"
  OP_PARAMS = [
    _PGroupName,
    ("ndparams", None, ht.TOr(ht.TDict, ht.TNone)),
    ("alloc_policy", None, ht.TOr(ht.TNone,
                                  ht.TElemOf(constants.VALID_ALLOC_POLICIES))),
    ]


class OpRemoveGroup(OpCode):
  """Remove a node group from the cluster."""
  OP_ID = "OP_GROUP_REMOVE"
  OP_DSC_FIELD = "group_name"
  OP_PARAMS = [
    _PGroupName,
    ]


class OpRenameGroup(OpCode):
  """Rename a node group in the cluster."""
  OP_ID = "OP_GROUP_RENAME"
  OP_DSC_FIELD = "old_name"
  OP_PARAMS = [
    ("old_name", ht.NoDefault, ht.TNonEmptyString),
    ("new_name", ht.NoDefault, ht.TNonEmptyString),
    ]


# OS opcodes
class OpDiagnoseOS(OpCode):
  """Compute the list of guest operating systems."""
  OP_ID = "OP_OS_DIAGNOSE"
  OP_PARAMS = [
    _POutputFields,
    ("names", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ]


# Exports opcodes
class OpQueryExports(OpCode):
  """Compute the list of exported images."""
  OP_ID = "OP_BACKUP_QUERY"
  OP_PARAMS = [
    ("nodes", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ("use_locking", False, ht.TBool),
    ]


class OpPrepareExport(OpCode):
  """Prepares an instance export.

  @ivar instance_name: Instance name
  @ivar mode: Export mode (one of L{constants.EXPORT_MODES})

  """
  OP_ID = "OP_BACKUP_PREPARE"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    ("mode", ht.NoDefault, ht.TElemOf(constants.EXPORT_MODES)),
    ]


class OpExportInstance(OpCode):
  """Export an instance.

  For local exports, the export destination is the node name. For remote
  exports, the export destination is a list of tuples, each consisting of
  hostname/IP address, port, HMAC and HMAC salt. The HMAC is calculated using
  the cluster domain secret over the value "${index}:${hostname}:${port}". The
  destination X509 CA must be a signed certificate.

  @ivar mode: Export mode (one of L{constants.EXPORT_MODES})
  @ivar target_node: Export destination
  @ivar x509_key_name: X509 key to use (remote export only)
  @ivar destination_x509_ca: Destination X509 CA in PEM format (remote export
                             only)

  """
  OP_ID = "OP_BACKUP_EXPORT"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    _PShutdownTimeout,
    # TODO: Rename target_node as it changes meaning for different export modes
    # (e.g. "destination")
    ("target_node", ht.NoDefault, ht.TOr(ht.TNonEmptyString, ht.TList)),
    ("shutdown", True, ht.TBool),
    ("remove_instance", False, ht.TBool),
    ("ignore_remove_failures", False, ht.TBool),
    ("mode", constants.EXPORT_MODE_LOCAL, ht.TElemOf(constants.EXPORT_MODES)),
    ("x509_key_name", None, ht.TOr(ht.TList, ht.TNone)),
    ("destination_x509_ca", None, ht.TMaybeString),
    ]


class OpRemoveExport(OpCode):
  """Remove an instance's export."""
  OP_ID = "OP_BACKUP_REMOVE"
  OP_DSC_FIELD = "instance_name"
  OP_PARAMS = [
    _PInstanceName,
    ]


# Tags opcodes
class OpGetTags(OpCode):
  """Returns the tags of the given object."""
  OP_ID = "OP_TAGS_GET"
  OP_DSC_FIELD = "name"
  OP_PARAMS = [
    _PTagKind,
    # Name is only meaningful for nodes and instances
    ("name", ht.NoDefault, ht.TMaybeString),
    ]


class OpSearchTags(OpCode):
  """Searches the tags in the cluster for a given pattern."""
  OP_ID = "OP_TAGS_SEARCH"
  OP_DSC_FIELD = "pattern"
  OP_PARAMS = [
    ("pattern", ht.NoDefault, ht.TNonEmptyString),
    ]


class OpAddTags(OpCode):
  """Add a list of tags on a given object."""
  OP_ID = "OP_TAGS_SET"
  OP_PARAMS = [
    _PTagKind,
    _PTags,
    # Name is only meaningful for nodes and instances
    ("name", ht.NoDefault, ht.TMaybeString),
    ]


class OpDelTags(OpCode):
  """Remove a list of tags from a given object."""
  OP_ID = "OP_TAGS_DEL"
  OP_PARAMS = [
    _PTagKind,
    _PTags,
    # Name is only meaningful for nodes and instances
    ("name", ht.NoDefault, ht.TMaybeString),
    ]

# Test opcodes
class OpTestDelay(OpCode):
  """Sleeps for a configured amount of time.

  This is used just for debugging and testing.

  Parameters:
    - duration: the time to sleep
    - on_master: if true, sleep on the master
    - on_nodes: list of nodes in which to sleep

  If the on_master parameter is true, it will execute a sleep on the
  master (before any node sleep).

  If the on_nodes list is not empty, it will sleep on those nodes
  (after the sleep on the master, if that is enabled).

  As an additional feature, the case of duration < 0 will be reported
  as an execution error, so this opcode can be used as a failure
  generator. The case of duration == 0 will not be treated specially.

  """
  OP_ID = "OP_TEST_DELAY"
  OP_DSC_FIELD = "duration"
  OP_PARAMS = [
    ("duration", ht.NoDefault, ht.TFloat),
    ("on_master", True, ht.TBool),
    ("on_nodes", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ("repeat", 0, ht.TPositiveInt)
    ]


class OpTestAllocator(OpCode):
  """Allocator framework testing.

  This opcode has two modes:
    - gather and return allocator input for a given mode (allocate new
      or replace secondary) and a given instance definition (direction
      'in')
    - run a selected allocator for a given operation (as above) and
      return the allocator output (direction 'out')

  """
  OP_ID = "OP_TEST_ALLOCATOR"
  OP_DSC_FIELD = "allocator"
  OP_PARAMS = [
    ("direction", ht.NoDefault,
     ht.TElemOf(constants.VALID_IALLOCATOR_DIRECTIONS)),
    ("mode", ht.NoDefault, ht.TElemOf(constants.VALID_IALLOCATOR_MODES)),
    ("name", ht.NoDefault, ht.TNonEmptyString),
    ("nics", ht.NoDefault, ht.TOr(ht.TNone, ht.TListOf(
      ht.TDictOf(ht.TElemOf(["mac", "ip", "bridge"]),
               ht.TOr(ht.TNone, ht.TNonEmptyString))))),
    ("disks", ht.NoDefault, ht.TOr(ht.TNone, ht.TList)),
    ("hypervisor", None, ht.TMaybeString),
    ("allocator", None, ht.TMaybeString),
    ("tags", ht.EmptyList, ht.TListOf(ht.TNonEmptyString)),
    ("mem_size", None, ht.TOr(ht.TNone, ht.TPositiveInt)),
    ("vcpus", None, ht.TOr(ht.TNone, ht.TPositiveInt)),
    ("os", None, ht.TMaybeString),
    ("disk_template", None, ht.TMaybeString),
    ("evac_nodes", None, ht.TOr(ht.TNone, ht.TListOf(ht.TNonEmptyString))),
    ]


class OpTestJobqueue(OpCode):
  """Utility opcode to test some aspects of the job queue.

  """
  OP_ID = "OP_TEST_JQUEUE"
  OP_PARAMS = [
    ("notify_waitlock", False, ht.TBool),
    ("notify_exec", False, ht.TBool),
    ("log_messages", ht.EmptyList, ht.TListOf(ht.TString)),
    ("fail", False, ht.TBool),
    ]


class OpTestDummy(OpCode):
  """Utility opcode used by unittests.

  """
  OP_ID = "OP_TEST_DUMMY"
  OP_PARAMS = [
    ("result", ht.NoDefault, ht.NoType),
    ("messages", ht.NoDefault, ht.NoType),
    ("fail", ht.NoDefault, ht.NoType),
    ]
  WITH_LU = False


def _GetOpList():
  """Returns list of all defined opcodes.

  Does not eliminate duplicates by C{OP_ID}.

  """
  return [v for v in globals().values()
          if (isinstance(v, type) and issubclass(v, OpCode) and
              hasattr(v, "OP_ID") and v is not OpCode)]


OP_MAPPING = dict((v.OP_ID, v) for v in _GetOpList())
